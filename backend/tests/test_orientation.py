"""Orientation layer c (Phase 4, owner change 1): the Reader judges which way up each answer page
is in the same call; a page judged not upright with confidence of at least 0.8 is turned and read
once more. Plus the image the model receives is turned by the page's effective rotation."""

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.mock import MockReader
from app.ai.ollama import OllamaReader, resolve_model
from app.ai.ollama_client import OllamaClient
from app.ai.types import PageImage, PageText
from app.ai.types import Transcription as AiTranscription
from app.db.models import AuditEvent, Page, Script, ScriptStatus, Transcription
from app.subjects.registry import SubjectConfig, get_registry
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, upload_pdf
from tests.fake_ollama import FakeOllama
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages


def _top_is_dark(image: Image.Image) -> bool:
    values = list(image.convert("L").resize((20, 20)).tobytes())
    return sum(values[:200]) < sum(values[200:])


def test_reader_sends_the_page_turned_by_its_rotation(tmp_path: Path) -> None:
    path = tmp_path / "page.jpg"
    image = Image.new("RGB", (600, 800), "white")
    image.paste((0, 0, 0), (0, 0, 600, 200))  # dark band at the top
    image.save(path, "JPEG")
    chemistry = get_registry().get("cm_gce_ol", "chemistry")
    assert chemistry is not None

    with FakeOllama() as fake:
        client = OllamaClient(fake.url, timeout_seconds=5)
        reader = OllamaReader(
            client,
            resolve_model(client, "qwen3-vl:4b-instruct"),
            max_image_px=800,
            output_retries=0,
        )
        fake.replies.append(
            json.dumps({"text": "t", "orientation": "upright", "orientation_confidence": 0.9})
        )
        result = reader.transcribe([PageImage(1, path, rotation=180)], chemistry)
        reader.transcribe([PageImage(1, path, rotation=90)], chemistry)

    sent = [
        Image.open(io.BytesIO(base64.b64decode(r["messages"][0]["images"][0])))
        for r in fake.requests
    ]
    assert not _top_is_dark(sent[0])  # turned 180: the dark band is now at the bottom
    assert sent[0].height > sent[0].width
    assert sent[1].width > sent[1].height  # a quarter turn swaps the sides
    assert (result.pages[0].orientation, result.pages[0].orientation_confidence) == (
        "upright",
        0.9,
    )
    # The stored file is never changed.
    assert _top_is_dark(Image.open(path))


class JudgingReader(MockReader):
    """Judges every page read without rotation as ``first``; pages read turned as ``second``."""

    def __init__(
        self,
        first: tuple[str | None, float | None],
        second: tuple[str | None, float | None] = ("upright", 0.99),
    ) -> None:
        super().__init__()
        self.first, self.second = first, second
        self.reads: list[tuple[int, int]] = []

    def transcribe(self, pages: list[PageImage], subject: SubjectConfig) -> AiTranscription:
        result = super().transcribe(pages, subject)
        page = pages[0]
        self.reads.append((page.page_id, page.rotation))
        orientation, confidence = self.first if page.rotation == 0 else self.second
        text = f"read at {page.rotation}"
        return AiTranscription(
            [PageText(page.page_id, text, orientation, confidence)],
            result.model,
            result.prompt_version,
            result.created_at,
        )


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def scanned(alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    """One student's script: cover + one answer page, fed upright."""
    factory.student(world.class_a, "AAAAAA")
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    upload_pdf(alice, exam["id"], ScanBuilder().add(covers[0]).add(answer_page(1)).build())
    return exam


def _run(
    app: FastAPI,
    alice: ApiUser,
    exam: dict[str, Any],
    reader: JudgingReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.worker.handlers.build_reader", lambda _s: reader)
    assert alice.post(f"/api/exams/{exam['id']}/ai-marking").status_code == 202
    run_jobs(app)


def _answer_page(db: Session) -> Page:
    return db.scalars(select(Page).where(Page.is_cover.is_(False))).one()


def test_confident_upside_down_page_is_turned_and_read_once_more(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = JudgingReader(("upside_down", 0.93))
    _run(app, alice, scanned, reader, monkeypatch)

    page = _answer_page(db)
    assert reader.reads == [(page.id, 0), (page.id, 180)]
    assert (page.rotation_auto, page.effective_rotation, page.auto_rotation_confidence) == (
        180,
        180,
        0.93,
    )
    assert page.auto_rotation_model == "mock-reader"
    assert page.auto_rotation_prompt_version is not None
    assert page.auto_rotation_prompt_version.startswith("reader-v2#")
    # Only the second read is kept.
    assert [t.text for t in db.scalars(select(Transcription))] == ["read at 180"]
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "auto_rotate")).one()
    assert (event.entity_type, event.entity_id, event.actor_id) == ("page", page.id, None)
    assert db.scalars(select(Script)).one().status == ScriptStatus.AI_MARKED


def test_sideways_page_is_turned_the_right_way(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = JudgingReader(("rotated_clockwise", 0.85))
    _run(app, alice, scanned, reader, monkeypatch)
    page = _answer_page(db)
    assert reader.reads == [(page.id, 0), (page.id, 270)]
    assert page.rotation_auto == 270


@pytest.mark.parametrize(
    "judgement",
    [("upside_down", 0.79), (None, None), ("upright", 1.0)],
    ids=["below-threshold", "invalid-judgement", "upright"],
)
def test_unconfident_or_missing_judgement_rotates_nothing(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    judgement: tuple[str | None, float | None],
) -> None:
    reader = JudgingReader(judgement)
    _run(app, alice, scanned, reader, monkeypatch)
    page = _answer_page(db)
    assert reader.reads == [(page.id, 0)]
    assert (page.rotation_auto, page.auto_rotation_confidence) == (0, None)
    assert [t.text for t in db.scalars(select(Transcription))] == ["read at 0"]
    assert not db.scalars(select(AuditEvent).where(AuditEvent.action == "auto_rotate")).all()


def test_second_read_never_triggers_another_rotation(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = JudgingReader(("upside_down", 0.99), second=("upside_down", 0.99))
    _run(app, alice, scanned, reader, monkeypatch)
    page = _answer_page(db)
    assert reader.reads == [(page.id, 0), (page.id, 180)]
    assert page.rotation_auto == 180


def test_off_switch_ignores_the_judgement(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.state.settings = app.state.settings.model_copy(update={"orientation_check": "off"})
    reader = JudgingReader(("upside_down", 0.99))
    _run(app, alice, scanned, reader, monkeypatch)
    page = _answer_page(db)
    assert reader.reads == [(page.id, 0)]
    assert page.rotation_auto == 0


def test_teacher_rotation_is_used_and_skips_the_judgement(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _answer_page(db)
    page.rotation_teacher = 90
    db.commit()
    reader = JudgingReader(("upside_down", 0.99), second=("upside_down", 0.99))
    _run(app, alice, scanned, reader, monkeypatch)
    db.refresh(page)
    assert reader.reads == [(page.id, 90)]
    assert page.rotation_auto == 0


def test_stack_rotation_from_the_cover_is_applied_before_reading(
    app: FastAPI,
    alice: ApiUser,
    world: World,
    factory: Factory,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory.student(world.class_a, "AAAAAA")
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    cover = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)[0]
    scan = ScanBuilder().add(cover, rotate=180).add(answer_page(1), rotate=180).build()
    upload_pdf(alice, exam["id"], scan)

    reader = JudgingReader(("upright", 0.99))
    _run(app, alice, exam, reader, monkeypatch)
    page = _answer_page(db)
    assert page.rotation_stack == 180
    assert reader.reads == [(page.id, 180)]  # read upright, no re-read needed
