"""Non-negotiable: the application only ever connects to the configured model host.

- Dynamic: run the whole pipeline with the Ollama implementations against a fake model server and
  record every outbound connection made in this process; anything but the model host fails.
- Static: only app/ai/ollama_client.py may import networking modules.
- Start-up: a public model host is refused unless explicitly allowed.
"""

import ast
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from app.config import Settings
from app.startup_checks import UnsafeConfigurationError, check_startup_safety, model_host_is_local
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, start_ai, upload_pdf
from tests.fake_ollama import FakeOllama
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages

APP_DIR = Path(__file__).resolve().parents[1] / "app"
NETWORK_MODULES = {"socket", "http.client", "urllib.request", "httpx", "requests", "aiohttp", "ssl"}


class OutboundConnectionError(AssertionError):
    pass


@pytest.fixture
def connections(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Record (host, port) of every outbound socket connection in this process.

    On Windows, ``socket.socketpair()`` is emulated with a loopback connect, which the event loop
    uses internally (in-process plumbing, not an outbound connection); those are ignored."""
    seen: list[tuple[str, int]] = []
    inside_socketpair = threading.local()
    original_connect = socket.socket.connect
    original_socketpair = socket.socketpair

    def recording_connect(self: socket.socket, address: Any) -> Any:
        if isinstance(address, tuple) and not getattr(inside_socketpair, "active", False):
            seen.append((str(address[0]), int(address[1])))
        return original_connect(self, address)

    def marked_socketpair(*args: Any, **kwargs: Any) -> Any:
        inside_socketpair.active = True
        try:
            return original_socketpair(*args, **kwargs)
        finally:
            inside_socketpair.active = False

    monkeypatch.setattr(socket.socket, "connect", recording_connect)
    monkeypatch.setattr(socket, "socketpair", marked_socketpair)
    return seen  # monkeypatch undoes the patches after the test


def test_full_pipeline_only_contacts_the_model_host(
    app: FastAPI,
    world: World,
    factory: Factory,
    settings: Settings,
    connections: list[tuple[str, int]],
) -> None:
    with FakeOllama() as fake:
        fake.default_reply = '{"text": "1(a) conducts electricity and malleable\\n1(b) hydrogen"}'

        def marker_reply(body: dict[str, Any]) -> str:
            # Award nothing; evidence empty is always valid. Point ids come from the prompt.
            import json
            import re

            # The prompt lists points as "- p<id> (...)"; reply in the per-question keyed shape.
            prompt = body["messages"][0]["content"]
            ids = re.findall(r"^- p(\d+) \(", prompt, re.MULTILINE)
            # Reply in the evidence shape the prompt asks for (line numbers or a quote).
            evidence: dict[str, Any] = (
                {"evidence_lines": []} if "evidence_lines" in prompt else {"evidence": ""}
            )
            return json.dumps(
                {
                    "points": {
                        f"p{i}": {
                            "awarded_marks": 0,
                            **evidence,
                            "confidence": 0.5,
                            "error_category": "omitted",
                        }
                        for i in ids
                    }
                }
            )

        app.state.settings = settings.model_copy(
            update={"ai_backend": "ollama", "model_base_url": fake.url}
        )
        alice = ApiUser(app, "alice")
        factory.student(world.class_a, "AAAAAA")
        exam = make_ready_exam(alice, world.class_a.id)
        alice.post(f"/api/exams/{exam['id']}/cover-sheets")
        cover = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)[0]
        upload_pdf(alice, exam["id"], ScanBuilder().add(cover).add(answer_page(1)).build())
        start_ai(alice, exam["id"])
        connections.clear()  # only what the pipeline does from here on
        # Reader replies come first (default), marker replies after.
        original_default = fake.default_reply
        fake.replies.append(original_default)
        fake.default_reply = marker_reply
        run_jobs(app)
        status = alice.get(f"/api/exams/{exam['id']}/ai-status").json()

    assert status["scripts"]["ai_marked"] == 1
    assert connections, "the pipeline should have talked to the model server"
    assert set(connections) == {("127.0.0.1", fake.port)}, connections


def test_guard_sees_a_connection_to_another_host(connections: list[tuple[str, int]]) -> None:
    with pytest.raises(urllib.error.URLError):
        # 192.0.2.1 is TEST-NET-1: reserved, never routed. The attempt itself is what we detect.
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            "http://192.0.2.1/", timeout=0.5
        )
    assert ("192.0.2.1", 80) in connections


def test_only_the_ollama_client_imports_networking_modules() -> None:
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == m or name.startswith(m + ".") for m in NETWORK_MODULES):
                    offenders.append((path.relative_to(APP_DIR).as_posix(), name))
    allowed = {
        ("ai/ollama_client.py", "http.client"),
        ("worker/runner.py", "socket"),
        ("services/ipp.py", "http.client"),
    }
    # worker/runner.py uses socket.gethostname() only, to name the worker (no connections).
    assert set(offenders) <= allowed, offenders


@pytest.mark.parametrize(
    ("url", "local"),
    [
        ("http://127.0.0.1:11434", True),
        ("http://localhost:11434", True),
        ("http://ollama:11434", True),
        ("http://192.168.1.20:11434", True),
        ("http://10.0.0.5:11434", True),
        ("http://school-server.local:11434", True),
        ("http://[::1]:11434", True),
        ("https://api.example.com", False),
        ("http://8.8.8.8:11434", False),
        ("http://ollama.example.org:11434", False),
    ],
)
def test_model_host_must_be_on_the_school_network(url: str, local: bool) -> None:
    assert model_host_is_local(url) is local


def test_public_model_host_refuses_to_start_unless_allowed(settings: Settings) -> None:
    public = settings.model_copy(update={"model_base_url": "https://api.example.com"})

    with pytest.raises(UnsafeConfigurationError, match="MARGIN_ALLOW_PUBLIC_MODEL_HOST"):
        check_startup_safety(public)
    check_startup_safety(public.model_copy(update={"allow_public_model_host": True}))
