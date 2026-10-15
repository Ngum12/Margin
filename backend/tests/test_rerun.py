"""Re-run AI marking (owner, 2026-10-15) and labelling of test-model output.

A re-run starts a new AI run for unconfirmed scripts; earlier proposals and decisions stay as
history and only the current run is shown. Output from the Mock models is labelled as "test
model" everywhere it appears: review, queue, results, CSV and marked PDFs."""

import csv
import io
from typing import Any

import pypdfium2 as pdfium
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.ai.mock import MockMarker, MockReader
from app.ai.types import ModelInfo
from app.config import get_settings
from app.db.models import AuditEvent, Exam, ExamStatus, MarkDecision, Script, ScriptStatus
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, start_ai, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages


class RealReader(MockReader):
    """Stands in for a real model: same behaviour as the Mock, a non-test model name."""

    def __init__(self) -> None:
        super().__init__()
        self.model = ModelInfo("qwen3-vl:4b-instruct", "ee4b975b58c1", "ollama")


class RealMarker(MockMarker):
    def __init__(self) -> None:
        super().__init__()
        self.model = ModelInfo("qwen3-vl:4b-instruct", "ee4b975b58c1", "ollama")


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def bruno(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "bruno")


@pytest.fixture
def marked(app: FastAPI, alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    """Two scripts marked by the Mock (test) models."""
    for code in ("AAAAAA", "BBBBBB"):
        factory.student(world.class_a, code)
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    scan = ScanBuilder()
    for i, cover in enumerate(covers):
        scan.add(cover).add(answer_page(i))
    upload_pdf(alice, exam["id"], scan.build())
    start_ai(alice, exam["id"])
    run_jobs(app)
    items = alice.get(f"/api/exams/{exam['id']}/queue").json()["items"]
    return {"exam_id": exam["id"], "a": items[0]["script_id"], "b": items[1]["script_id"]}


def _use_real_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.worker.handlers.build_reader", lambda _s: RealReader())
    monkeypatch.setattr("app.worker.handlers.build_marker", lambda _s: RealMarker())


def _points(review: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for q in review["questions"] for p in q["points"]]


# --- labels -----------------------------------------------------------------------------------


def test_test_model_output_is_labelled_on_every_screen(
    alice: ApiUser, marked: dict[str, Any]
) -> None:
    review = alice.get(f"/api/scripts/{marked['a']}/review").json()
    assert review["test_model"] is True
    queue = alice.get(f"/api/exams/{marked['exam_id']}/queue").json()
    assert [i["test_model"] for i in queue["items"]] == [True, True]
    assert queue["test_model_count"] == 2
    results = alice.get(f"/api/exams/{marked['exam_id']}/results").json()
    assert results["test_model_count"] == 2
    assert all(r["test_model"] for r in results["rows"])


def test_review_shows_model_name_and_version_for_every_mark_and_transcription(
    alice: ApiUser, marked: dict[str, Any]
) -> None:
    review = alice.get(f"/api/scripts/{marked['a']}/review").json()
    for point in _points(review):
        assert (point["model_name"], point["model_version"]) == ("mock-marker", "mock-1")
        assert point["prompt_version"].startswith("marker-lines-v2#")
    answer = next(p for p in review["pages"] if not p["is_cover"])
    version = answer["transcription"]
    assert (version["model_name"], version["model_version"]) == ("mock-reader", "mock-1")
    assert version["prompt_version"].startswith("reader-v2#")


def test_csv_and_marked_pdf_label_test_model_output(alice: ApiUser, marked: dict[str, Any]) -> None:
    for script_id in (marked["a"], marked["b"]):
        alice.post(f"/api/scripts/{script_id}/accept-all")
        alice.post(f"/api/scripts/{script_id}/confirm")
    content = alice.get(f"/api/exams/{marked['exam_id']}/results.csv").content
    header, *rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    assert header[-1] == "AI model"
    assert [r[-1] for r in rows] == ["Test model: not real AI marking"] * 2

    pdf = pdfium.PdfDocument(alice.get(f"/api/scripts/{marked['a']}/marked.pdf").content)
    try:
        for index in range(len(pdf)):
            text = pdf[index].get_textpage().get_text_range()
            assert "TEST MODEL: NOT REAL AI MARKING" in text
    finally:
        pdf.close()


# --- re-run -------------------------------------------------------------------------------------


def test_rerun_with_a_real_model_replaces_what_is_shown_and_keeps_history(
    app: FastAPI,
    alice: ApiUser,
    marked: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_id = marked["a"]
    first = _points(alice.get(f"/api/scripts/{script_id}/review").json())[0]["id"]
    alice.put(f"/api/scripts/{script_id}/decisions/{first}", json={"marks": 0})
    before = len(db.scalars(select(MarkDecision).where(MarkDecision.script_id == script_id)).all())

    _use_real_models(monkeypatch)
    response = alice.post(f"/api/scripts/{script_id}/rerun-ai")

    assert response.status_code == 202
    assert response.json()["script"]["status"] == "waiting"
    assert alice.get(f"/api/exams/{marked['exam_id']}").json()["status"] == "marking"
    run_jobs(app)
    review = alice.get(f"/api/scripts/{script_id}/review").json()
    assert review["script"]["status"] == "ai_marked"
    assert (review["test_model"], review["ai_run"]) == (False, 1)
    points = _points(review)
    assert all(p["model_name"] == "qwen3-vl:4b-instruct" for p in points)
    assert all(p["final_marks"] is None for p in points)  # the teacher reviews the new run
    answer = next(p for p in review["pages"] if not p["is_cover"])
    assert answer["transcription"]["model_name"] == "qwen3-vl:4b-instruct"  # read again
    assert [v["model_name"] for v in answer["versions"]] == ["mock-reader", "qwen3-vl:4b-instruct"]
    # History: the first run's rows, including the teacher's decision, are kept.
    rows = db.scalars(select(MarkDecision).where(MarkDecision.script_id == script_id)).all()
    assert len(rows) == 2 * before
    assert {r.ai_run for r in rows} == {0, 1}
    assert any(r.ai_run == 0 and r.final_half_marks == 0 for r in rows)
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "rerun_ai")).one()
    assert (event.entity_type, event.entity_id, event.old_value["ai_run"]) == (
        "script",
        script_id,
        0,
    )
    assert event.new_value == {"ai_run": 1, "status": "waiting"}
    assert event.actor_id is not None
    # The exam is reviewable again once the AI is done.
    assert alice.get(f"/api/exams/{marked['exam_id']}").json()["status"] == "reviewing"
    queue = alice.get(f"/api/exams/{marked['exam_id']}/queue").json()
    assert {i["script_id"]: i["test_model"] for i in queue["items"]}[script_id] is False


def test_rerun_with_the_same_model_marks_the_teachers_edited_text(
    app: FastAPI, alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["a"]
    review = alice.get(f"/api/scripts/{script_id}/review").json()
    page_id = next(p for p in review["pages"] if not p["is_cover"])["id"]
    alice.post(f"/api/pages/{page_id}/transcription", json={"text": "1(a) shiny and malleable"})

    alice.post(f"/api/scripts/{script_id}/rerun-ai")
    run_jobs(app)

    review = alice.get(f"/api/scripts/{script_id}/review").json()
    answer = next(p for p in review["pages"] if not p["is_cover"])
    assert answer["transcription"]["source"] == "teacher"  # not read again: same reader
    assert len(answer["versions"]) == 2
    first, second, _third = _points(review)
    assert first["proposed_marks"] == 0  # "conducts electricity" is no longer in the text
    assert second["proposed_marks"] == 1  # "malleable" is
    assert review["ai_run"] == 1


def test_confirmed_scripts_and_running_ones_cannot_be_rerun(
    app: FastAPI, alice: ApiUser, marked: dict[str, Any]
) -> None:
    script_id = marked["a"]
    alice.post(f"/api/scripts/{script_id}/accept-all")
    alice.post(f"/api/scripts/{script_id}/confirm")
    refused = alice.post(f"/api/scripts/{script_id}/rerun-ai")
    assert (refused.status_code, refused.json()["code"]) == (409, "script.confirmed")

    other = marked["b"]
    assert alice.post(f"/api/scripts/{other}/rerun-ai").status_code == 202
    again = alice.post(f"/api/scripts/{other}/rerun-ai")  # the AI is already on it
    assert (again.status_code, again.json()["code"]) == (409, "ai.in_progress")


def test_exam_rerun_skips_confirmed_scripts(
    app: FastAPI,
    alice: ApiUser,
    marked: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice.post(f"/api/scripts/{marked['a']}/accept-all")
    alice.post(f"/api/scripts/{marked['a']}/confirm")
    _use_real_models(monkeypatch)

    response = alice.post(f"/api/exams/{marked['exam_id']}/rerun-ai")

    assert response.status_code == 202
    assert response.json() == {"scripts_queued": 1}
    run_jobs(app)
    a, b = db.get_one(Script, marked["a"]), db.get_one(Script, marked["b"])
    db.refresh(a)
    db.refresh(b)
    assert (a.status, a.ai_run) == (ScriptStatus.CONFIRMED, 0)  # untouched
    assert (b.status, b.ai_run) == (ScriptStatus.AI_MARKED, 1)
    exam_event = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "rerun_ai", AuditEvent.entity_type == "exam")
    ).one()
    assert exam_event.new_value == {"scripts": 1}

    alice.post(f"/api/scripts/{marked['b']}/accept-all")
    alice.post(f"/api/scripts/{marked['b']}/confirm")
    nothing = alice.post(f"/api/exams/{marked['exam_id']}/rerun-ai")
    assert (nothing.status_code, nothing.json()["code"]) == (409, "ai.nothing_to_rerun")


def test_another_teacher_cannot_rerun(
    alice: ApiUser, bruno: ApiUser, marked: dict[str, Any]
) -> None:
    assert bruno.post(f"/api/scripts/{marked['a']}/rerun-ai").status_code == 404
    assert bruno.post(f"/api/exams/{marked['exam_id']}/rerun-ai").status_code == 404


def test_cli_rerun_queues_the_exam_with_a_real_backend_only(
    app: FastAPI,
    marked: dict[str, Any],
    db: Session,
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MARGIN_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("MARGIN_ENV", "test")
    monkeypatch.setenv("MARGIN_AI_BACKEND", "mock")
    get_settings.cache_clear()
    try:
        assert cli.main(["rerun-ai", "--exam", str(marked["exam_id"])]) == 1
        assert "MARGIN_AI_BACKEND is mock" in capsys.readouterr().err

        monkeypatch.setenv("MARGIN_AI_BACKEND", "ollama")
        get_settings.cache_clear()
        assert cli.main(["rerun-ai", "--exam", "999"]) == 1
        assert cli.main(["rerun-ai", "--exam", str(marked["exam_id"])]) == 0
    finally:
        get_settings.cache_clear()

    db.expire_all()
    scripts = db.scalars(select(Script)).all()
    assert [(s.status, s.ai_run) for s in scripts] == [(ScriptStatus.WAITING, 1)] * 2
    assert db.get_one(Exam, marked["exam_id"]).status == ExamStatus.MARKING
    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "rerun_ai")).all()
    assert all(e.actor_id is None for e in events)  # the system, from the command line
