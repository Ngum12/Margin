"""AI pipeline with the Mock models: upload -> processed -> transcribed -> ai_marked."""

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.mock import MockMarker, MockReader
from app.ai.types import ModelCallTimeoutError, ModelOutputInvalidError, ModelUnavailableError
from app.db.models import (
    AuditEvent,
    ErrorCategory,
    Job,
    JobStatus,
    MarkDecision,
    ModelVersion,
    Page,
    Script,
    ScriptStatus,
    Transcription,
)
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, start_ai, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def scanned(alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    """Ready exam with two students' scripts uploaded and split (cover + 2 answer pages each)."""
    for code in ("AAAAAA", "BBBBBB"):
        factory.student(world.class_a, code)
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    scan = ScanBuilder()
    for i, cover in enumerate(covers):
        scan.add(cover).add(answer_page(2 * i)).add(answer_page(2 * i + 1))
    upload_pdf(alice, exam["id"], scan.build())
    return exam


def test_full_exam_goes_from_upload_to_ai_marked(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    response = start_ai(alice, scanned["id"])
    assert response.status_code == 202
    assert response.json() == {"scripts_queued": 2}
    assert alice.get(f"/api/exams/{scanned['id']}").json()["status"] == "marking"

    run_jobs(app)

    scripts = db.scalars(select(Script)).all()
    assert [s.status for s in scripts] == [ScriptStatus.AI_MARKED] * 2
    assert alice.get(f"/api/exams/{scanned['id']}").json()["status"] == "reviewing"
    summary = next(e for e in alice.get("/api/exams").json() if e["id"] == scanned["id"])
    assert summary["scripts"] == {"waiting": 0, "ai_marked": 2, "confirmed": 0}


def test_cover_sheets_are_not_transcribed_and_outputs_carry_versions(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    start_ai(alice, scanned["id"])
    run_jobs(app)

    transcriptions = db.scalars(select(Transcription)).all()
    covers = {p.id for p in db.scalars(select(Page).where(Page.is_cover.is_(True)))}
    assert len(transcriptions) == 4  # 2 answer pages x 2 scripts
    assert not {t.page_id for t in transcriptions} & covers
    for t in transcriptions:
        assert (t.model_name, t.model_version) == ("mock-reader", "mock-1")
        assert t.prompt_version is not None
        assert t.prompt_version.startswith("reader-v2#")
        assert t.created_at is not None
    decisions = db.scalars(select(MarkDecision)).all()
    assert len(decisions) == 2 * 3  # 3 mark scheme points per script
    for d in decisions:
        assert (d.model_name, d.model_version) == ("mock-marker", "mock-1")
        assert d.prompt_version is not None
        assert d.prompt_version.startswith("marker-lines-v2#")
        assert d.final_half_marks is None  # the AI never finalises a mark
    assert {(m.name, m.role.value) for m in db.scalars(select(ModelVersion))} == {
        ("mock-reader", "reader"),
        ("mock-marker", "marker"),
    }


def test_mock_marker_quotes_evidence_from_the_transcription(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    start_ai(alice, scanned["id"])
    run_jobs(app)
    script = db.scalars(select(Script)).first()
    assert script is not None

    results = alice.get(f"/api/scripts/{script.id}/ai-results").json()

    text = " ".join(t["text"] for t in results["transcriptions"])
    for decision in results["decisions"]:
        if decision["proposed_marks"] > 0:
            assert decision["evidence"].casefold() in text.casefold()
            assert decision["error_category"] == ErrorCategory.CORRECT.value


def test_running_again_does_not_duplicate_results(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    start_ai(alice, scanned["id"])
    run_jobs(app)
    start_ai(alice, scanned["id"])  # nothing left to queue
    run_jobs(app)

    assert len(db.scalars(select(Transcription)).all()) == 4
    assert len(db.scalars(select(MarkDecision)).all()) == 6


def test_reader_invalid_output_flags_script_for_manual_marking(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenReader(MockReader):
        def transcribe(self, pages, subject):  # type: ignore[no-untyped-def]
            raise ModelOutputInvalidError("reader_schema")

    monkeypatch.setattr("app.worker.handlers.build_reader", lambda _s: BrokenReader())
    start_ai(alice, scanned["id"])
    run_jobs(app)

    scripts = db.scalars(select(Script)).all()
    assert [s.manual_reason for s in scripts] == ["ai.reader_invalid_output"] * 2
    assert db.scalars(select(Transcription)).all() == []  # nothing invented
    status = alice.get(f"/api/exams/{scanned['id']}/ai-status").json()
    assert [f["reason"] for f in status["flagged"]] == ["ai.reader_invalid_output"] * 2
    assert alice.get(f"/api/exams/{scanned['id']}").json()["status"] == "reviewing"
    assert db.scalars(select(AuditEvent).where(AuditEvent.action == "flag_manual")).first()


def test_marker_failure_on_one_question_keeps_the_others_and_flags(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HalfMarker(MockMarker):
        def mark(self, transcription, exam):  # type: ignore[no-untyped-def]
            proposal = super().mark(transcription, exam)
            failed = proposal.questions[0].question_id
            return type(proposal)(
                proposal.questions[1:],
                proposal.model,
                proposal.prompt_version,
                proposal.created_at,
                (failed,),
            )

    monkeypatch.setattr("app.worker.handlers.build_marker", lambda _s: HalfMarker())
    start_ai(alice, scanned["id"])
    run_jobs(app)

    scripts = db.scalars(select(Script)).all()
    assert [s.manual_reason for s in scripts] == ["ai.marker_invalid_output"] * 2
    assert [s.status for s in scripts] == [ScriptStatus.TRANSCRIBED] * 2
    # Question 1(a) has 2 points (failed, not stored); question 1(b) has 1 point (stored).
    assert len(db.scalars(select(MarkDecision)).all()) == 2


def test_model_server_down_retries_with_backoff(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_settings: object) -> None:
        raise ModelUnavailableError("ConnectionRefusedError")

    monkeypatch.setattr("app.worker.handlers.build_reader", unavailable)
    start_ai(alice, scanned["id"])
    run_jobs(app)

    jobs = db.scalars(select(Job).where(Job.type == "transcribe_script")).all()
    assert all(j.status == JobStatus.QUEUED and j.attempts == 1 for j in jobs)
    assert all(j.last_error and j.last_error.startswith("model_unavailable") for j in jobs)
    assert [s.status for s in db.scalars(select(Script))] == [ScriptStatus.WAITING] * 2
    # The web app keeps working and reports what is going on.
    status = alice.get(f"/api/exams/{scanned['id']}/ai-status").json()
    assert status["jobs_queued"] == 2


def test_start_requires_scripts_and_a_ready_exam(alice: ApiUser, world: World) -> None:
    exam = make_ready_exam(alice, world.class_a.id)
    draft = alice.post(
        "/api/exams", json={"class_id": world.class_a.id, "subject_code": "chemistry", "title": "D"}
    ).json()

    assert alice.post(f"/api/exams/{exam['id']}/ai-marking").json()["code"] == "ai.no_scripts"
    assert alice.post(f"/api/exams/{draft['id']}/ai-marking").status_code == 409


def test_other_teacher_cannot_start_or_read_results(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    bruno = ApiUser(app, "bruno")
    script = db.scalars(select(Script)).first()
    assert script is not None

    assert bruno.post(f"/api/exams/{scanned['id']}/ai-marking").status_code == 404
    assert bruno.get(f"/api/exams/{scanned['id']}/ai-status").status_code == 404
    assert bruno.get(f"/api/scripts/{script.id}/ai-results").status_code == 404


def test_tray_pages_cannot_join_a_script_once_marking_started(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any], db: Session
) -> None:
    upload_pdf(alice, scanned["id"], ScanBuilder().add(answer_page(99)).build())
    start_ai(alice, scanned["id"])
    run_jobs(app)
    page = alice.get(f"/api/exams/{scanned['id']}/unassigned-pages").json()[0]
    script = db.scalars(select(Script)).first()
    assert script is not None

    response = alice.post(
        f"/api/exams/{scanned['id']}/pages/assign",
        json={"page_ids": [page["id"]], "student_id": script.student_id},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "script.locked"


def test_system_status_reports_worker_and_mock_backend(
    app: FastAPI, alice: ApiUser, scanned: dict[str, Any]
) -> None:
    before = alice.get("/api/system/status").json()
    from app.worker.runner import Worker

    Worker(app.state.sessionmaker, app.state.settings).beat()
    after = alice.get("/api/system/status").json()

    assert before["worker_online"] is False
    assert after["worker_online"] is True
    assert after["ai_backend"] == "mock"
    assert after["model_server_reachable"] is True


def test_reader_time_out_flags_the_script_with_its_own_reason(
    app: FastAPI,
    alice: ApiUser,
    scanned: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner, 2026-10-15: a page that never finishes is invalid output, not a server outage."""

    class SlowReader(MockReader):
        def transcribe(self, pages, subject):  # type: ignore[no-untyped-def]
            raise ModelCallTimeoutError

    monkeypatch.setattr("app.worker.handlers.build_reader", lambda _s: SlowReader())
    start_ai(alice, scanned["id"])
    run_jobs(app)

    scripts = db.scalars(select(Script)).all()
    assert [s.manual_reason for s in scripts] == ["ai.reader_timeout"] * 2
    jobs = db.scalars(select(Job).where(Job.type == "transcribe_script")).all()
    assert all(j.status == JobStatus.SUCCEEDED for j in jobs)  # not retried as an outage
