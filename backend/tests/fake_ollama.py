"""A tiny fake Ollama server on 127.0.0.1 for tests: records requests, replays scripted replies."""

import json
import threading
from collections import deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

Reply = str | Callable[[dict[str, Any]], str]


class FakeOllama:
    def __init__(self, models: dict[str, str] | None = None) -> None:
        self.models = models if models is not None else {"qwen3-vl:8b": "sha256:" + "ab" * 32}
        self.requests: list[dict[str, Any]] = []
        self.replies: deque[Reply] = deque()
        self.default_reply: Reply = json.dumps({"text": "fake transcription"})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def __enter__(self) -> "FakeOllama":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:  # keep test output quiet
                return

            def _send(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path == "/api/tags":
                    models = [{"name": n, "digest": d} for n, d in fake.models.items()]
                    self._send(200, {"models": models})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                if self.path != "/api/chat":
                    self._send(404, {"error": "not found"})
                    return
                reply = fake.replies.popleft() if fake.replies else fake.default_reply
                content = reply(body) if callable(reply) else reply
                self._send(
                    200,
                    {
                        "model": body["model"],
                        "message": {"role": "assistant", "content": content},
                        "done": True,
                    },
                )

        return Handler
