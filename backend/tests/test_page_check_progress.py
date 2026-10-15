"""Page check before AI marking, and live AI progress (owner, 2026-10-15)."""

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.mock import MockMarker, MockReader
from app.ai.types import PageImage
from app.ai.types import Transcription as AiTranscription
from app.db.models import AuditEvent, Exam, ModelCall, ModelRole, Script
from app.subjects.registry import SubjectConfig
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, start_ai, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def bruno(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "bruno")


def _scan(alice: ApiUser, exam_id: int, covers: list[Any], pages_each: int = 1) -> None:
    scan = ScanBuilder()
    for i, cover in enumerate(covers):
        scan.add(cover)
        for n in range(pages_each):
            scan.add(answer_page(10 * i + n))
    upload_pdf(alice, exam_id, scan.build())


@pytest.fixture
def scanned(alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    """Two students: AAAAAA with two answer pages, BBBBBB with one (uploaded separately)."""
    for code in ("AAAAAA", "BBBBBB"):
        factory.student(world.class_a, code)
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    _scan(alice, exam["id"], covers[:1], pages_each=2)
    return {"exam_id": exam["id"], "covers": covers}


# --- page check -------------------------------------------------------------------------------


def test_page_check_lists_every_page_with_its_orientation(
    alice: ApiUser, scanned: dict[str, Any]
) -> None:
    body = alice.get(f"/api/exams/{scanned['exam_id']}/page-check").json()
    assert body["checked_at"] is None
    [script] = body["scripts"]
    assert script["student_code"] == "AAAAAA"
    assert [p["is_cover"] for p in script["pages"]] == [True, False, False]
    assert all(p["rotation"] == 0 for p in script["pages"])


def test_ai_marking_waits_until_the_pages_are_checked(
    alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    exam_id = scanned["exam_id"]
    refused = alice.post(f"/api/exams/{exam_id}/ai-marking")
    assert (refused.status_code, refused.json()["code"]) == (409, "exam.pages_not_checked")

    page = alice.get(f"/api/exams/{exam_id}/page-check").json()["scripts"][0]["pages"][1]
    alice.post(f"/api/pages/{page['id']}/rotation", json={"rotation": 180})
    checked = alice.post(f"/api/exams/{exam_id}/page-check").json()
    assert checked["checked_at"] is not None
    assert checked["scripts"][0]["pages"][1]["rotation"] == 180

    assert alice.post(f"/api/exams/{exam_id}/ai-marking").status_code == 202
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "pages_checked")).one()
    assert (event.entity_type, event.entity_id) == ("exam", exam_id)


def test_a_new_upload_clears_the_check_and_blocks_a_rerun(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    exam_id = scanned["exam_id"]
    start_ai(alice, exam_id)
    run_jobs(app)

    _scan(alice, exam_id, scanned["covers"][1:])  # BBBBBB's pages arrive later

    assert db.get_one(Exam, exam_id).pages_checked_at is None
    refused = alice.post(f"/api/exams/{exam_id}/rerun-ai")
    assert (refused.status_code, refused.json()["code"]) == (409, "exam.pages_not_checked")
    assert alice.post(f"/api/exams/{exam_id}/page-check").status_code == 200
    assert alice.post(f"/api/exams/{exam_id}/ai-marking").status_code == 202


def test_pages_assigned_from_the_tray_clear_the_check(
    alice: ApiUser, scanned: dict[str, Any], world: World, db: Session
) -> None:
    exam_id = scanned["exam_id"]
    alice.post(f"/api/exams/{exam_id}/page-check")
    upload_pdf(alice, exam_id, ScanBuilder().add(answer_page(99)).build(), "stray.pdf")
    stray = alice.get(f"/api/exams/{exam_id}/unassigned-pages").json()[0]
    student = db.scalar(select(Script.student_id).where(Script.exam_id == exam_id))
    alice.post(
        f"/api/exams/{exam_id}/pages/assign",
        json={"page_ids": [stray["id"]], "student_id": student},
    )
    assert db.get_one(Exam, exam_id).pages_checked_at is None


def test_another_teacher_cannot_see_or_check_the_pages(
    bruno: ApiUser, scanned: dict[str, Any]
) -> None:
    assert bruno.get(f"/api/exams/{scanned['exam_id']}/page-check").status_code == 404
    assert bruno.post(f"/api/exams/{scanned['exam_id']}/page-check").status_code == 404
    assert bruno.get(f"/api/exams/{scanned['exam_id']}/ai-progress").status_code == 404


# --- live progress ----------------------------------------------------------------------------


def test_progress_before_during_and_after_a_run(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exam_id = scanned["exam_id"]
    url = f"/api/exams/{exam_id}/ai-progress"
    before = alice.get(url).json()
    assert before["running"] is False
    assert [s["state"] for s in before["scripts"]] == ["idle"]

    seen: list[tuple[str | None, int | None, int | None, bool]] = []
    factory = app.state.sessionmaker

    def snapshot() -> None:
        with factory() as other:
            script = other.scalars(select(Script)).one()
            seen.append(
                (
                    script.ai_step,
                    script.ai_step_index,
                    script.ai_step_total,
                    script.ai_step_page_id is not None,
                )
            )

    class WatchedReader(MockReader):
        def transcribe(self, pages: list[PageImage], subject: SubjectConfig) -> AiTranscription:
            snapshot()
            return super().transcribe(pages, subject)

    class WatchedMarker(MockMarker):
        def mark(self, transcription, exam):  # type: ignore[no-untyped-def]
            outer = self.on_question

            def hook(number: int, total: int) -> None:
                if outer:
                    outer(number, total)
                snapshot()

            self.on_question = hook
            return super().mark(transcription, exam)

    monkeypatch.setattr("app.worker.handlers.build_reader", lambda _s: WatchedReader())
    monkeypatch.setattr("app.worker.handlers.build_marker", lambda _s: WatchedMarker())
    start_ai(alice, exam_id)

    queued = alice.get(url).json()
    assert queued["running"] is True
    assert [s["state"] for s in queued["scripts"]] == ["queued"]
    assert queued["eta_seconds"] is None  # nothing measured yet: no guess
    assert (queued["done_units"], queued["total_units"]) == (0, 2 + 2)  # 2 pages + 2 questions

    run_jobs(app)

    assert seen == [
        ("reading", 1, 2, True),
        ("reading", 2, 2, True),
        ("marking", 1, 2, False),
        ("marking", 2, 2, False),
    ]
    after = alice.get(url).json()
    assert after["running"] is False
    assert (after["percent"], after["ready"], after["manual"]) == (100, 1, 0)
    assert after["latest_read"]["student_code"] == "AAAAAA"
    assert after["latest_read"]["text"].startswith("1(a)")
    script = db.scalars(select(Script)).one()
    db.refresh(script)
    assert script.ai_step is None  # idle again
    calls = db.scalars(select(ModelCall)).all()
    assert sorted(c.role.value for c in calls) == ["marker", "marker", "reader", "reader"]
    assert all(c.seconds >= 0 and c.model_name.startswith("mock-") for c in calls)


def test_time_left_comes_from_measured_calls(
    alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    db.add_all(
        [
            ModelCall(role=ModelRole.READER, model_name="m", seconds=90.0),
            ModelCall(role=ModelRole.READER, model_name="m", seconds=110.0),
            ModelCall(role=ModelRole.MARKER, model_name="m", seconds=50.0),
        ]
    )
    db.commit()
    start_ai(alice, scanned["exam_id"])

    body = alice.get(f"/api/exams/{scanned['exam_id']}/ai-progress").json()

    # 2 pages x 100 s average + 2 questions x 50 s.
    assert body["eta_seconds"] == 300
    assert body["percent"] == 0
