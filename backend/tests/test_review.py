"""Teacher review (Phase 4): queue, script review, every edit and its audit event, confirm and
reopen, locking, manual marking, orientation controls, review time, export guard, permissions."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.mock import MockReader
from app.ai.types import ModelOutputInvalidError
from app.db.models import (
    AuditEvent,
    Exam,
    MarkDecision,
    MarkSchemePoint,
    Page,
    ReviewSession,
    Script,
    ScriptStatus,
    Transcription,
)
from app.errors import ConflictError
from app.schemas.review import QueueItemOut
from app.services import exports
from app.services.review import _queue_order
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, start_ai, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def bruno(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "bruno")


def _scan_exam(alice: ApiUser, world: World, factory: Factory, codes: tuple[str, ...]) -> int:
    for code in codes:
        factory.student(world.class_a, code)
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    scan = ScanBuilder()
    for i, cover in enumerate(covers):
        scan.add(cover).add(answer_page(i))
    upload_pdf(alice, exam["id"], scan.build())
    return int(exam["id"])


@pytest.fixture
def marked(app: FastAPI, alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    """Two scripts marked by the Mock models (every point proposed at full marks)."""
    exam_id = _scan_exam(alice, world, factory, ("AAAAAA", "BBBBBB"))
    start_ai(alice, exam_id)
    run_jobs(app)
    queue = alice.get(f"/api/exams/{exam_id}/queue").json()
    return {"exam_id": exam_id, "script_ids": [i["script_id"] for i in queue["items"]]}


def _review(user: ApiUser, script_id: int) -> dict[str, Any]:
    response = user.get(f"/api/scripts/{script_id}/review")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _events(db: Session, action: str | None = None) -> list[AuditEvent]:
    query = select(AuditEvent).order_by(AuditEvent.id)
    if action:
        query = query.where(AuditEvent.action == action)
    return list(db.scalars(query))


def _points(review: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for q in review["questions"] for p in q["points"]]


def _answer_page(review: dict[str, Any]) -> dict[str, Any]:
    page: dict[str, Any] = next(p for p in review["pages"] if not p["is_cover"])
    return page


# --- queue and review payload -----------------------------------------------------------------


def test_queue_lists_every_script_with_its_summary(alice: ApiUser, marked: dict[str, Any]) -> None:
    queue = alice.get(f"/api/exams/{marked['exam_id']}/queue").json()
    assert [i["student_code"] for i in queue["items"]] == ["AAAAAA", "BBBBBB"]
    item = queue["items"][0]
    assert item["status"] == "ai_marked"
    assert item["reviewable"] is True
    assert (item["decided_points"], item["total_points"]) == (0, 3)
    assert (item["proposed_total"], item["final_total"], item["max_total"]) == (3, None, 3)
    assert item["deductions"] == 0
    assert item["page_count"] == 2
    assert queue["average_review_seconds"] is None
    assert queue["confirmed_count"] == 0


def test_review_shows_pages_transcriptions_points_and_proposals(
    alice: ApiUser, marked: dict[str, Any]
) -> None:
    review = _review(alice, marked["script_ids"][0])
    assert review["ready"] is True
    assert review["locked"] is False
    assert review["can_confirm"] is False
    assert review["script"]["student_code"] == "AAAAAA"
    page = _answer_page(review)
    assert page["transcription"]["text"].startswith("1(a) Metals conduct electricity")
    assert page["transcription"]["source"] == "model"
    assert page["rotation"] == 0
    assert page["auto_rotated"] is False
    assert [q["label"] for q in review["questions"]] == ["1(a)", "1(b)"]
    point = review["questions"][0]["points"][0]
    assert point["proposed_marks"] == 1
    assert point["max_marks"] == 1
    assert point["evidence"]
    assert point["confidence"] is not None
    assert point["final_marks"] is None
    assert review["navigation"] == {
        "previous_id": None,
        "next_id": marked["script_ids"][1],
        "position": 1,
        "count": 2,
    }


def test_deductions_are_counted_per_point_and_question(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    """Owner, 2026-10-15: where the AI proposed fewer marks than a point's maximum."""
    script_id = marked["script_ids"][0]
    decision = db.scalars(
        select(MarkDecision).where(MarkDecision.script_id == script_id).order_by(MarkDecision.id)
    ).first()
    assert decision is not None
    decision.proposed_half_marks = 0
    db.commit()

    review = _review(alice, script_id)
    first = review["questions"][0]
    assert [p["deducted"] for p in first["points"]] == [1, 0]
    assert (first["deductions"], first["marks_deducted"], first["proposed_total"]) == (1, 1, 1)
    assert review["questions"][1]["deductions"] == 0
    assert (review["totals"]["deductions"], review["totals"]["marks_deducted"]) == (1, 1)
    item = alice.get(f"/api/exams/{marked['exam_id']}/queue").json()["items"][0]
    assert (item["deductions"], item["marks_deducted"]) == (1, 1)


# --- decisions --------------------------------------------------------------------------------


def test_set_marks_and_category_is_audited_and_starts_review(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    point_id = _points(_review(alice, script_id))[0]["id"]

    review = alice.put(f"/api/scripts/{script_id}/decisions/{point_id}", json={"marks": 0}).json()

    point = _points(review)[0]
    # A fresh decision takes the AI's category when none is given.
    assert (point["final_marks"], point["final_category"]) == (0, "correct")
    assert review["script"]["status"] == "in_review"
    assert review["script"]["reviewed_at"] is not None
    review = alice.put(
        f"/api/scripts/{script_id}/decisions/{point_id}", json={"category": "conceptual_error"}
    ).json()
    assert _points(review)[0]["final_category"] == "conceptual_error"

    events = _events(db, "set_decision")
    assert [(e.old_value, e.new_value) for e in events] == [
        ({"marks": None, "category": None}, {"marks": 0, "category": "correct"}),
        ({"marks": 0, "category": "correct"}, {"marks": 0, "category": "conceptual_error"}),
    ]
    assert all(e.actor_id is not None and e.entity_type == "mark_decision" for e in events)


@pytest.mark.parametrize("marks", [2, -1, 0.5])
def test_marks_outside_the_point_or_not_whole_are_refused(
    alice: ApiUser, marked: dict[str, Any], marks: float, db: Session
) -> None:
    script_id = marked["script_ids"][0]
    point_id = _points(_review(alice, script_id))[0]["id"]
    response = alice.put(f"/api/scripts/{script_id}/decisions/{point_id}", json={"marks": marks})
    assert response.status_code == 422
    assert response.json()["code"] == "decision.marks_out_of_range"
    assert _events(db, "set_decision") == []


def test_point_of_another_exam_is_not_found(
    alice: ApiUser, marked: dict[str, Any], world: World
) -> None:
    other = make_ready_exam(alice, world.class_a.id, "Other")
    other_point = other["questions"][0]["points"][0]["id"]
    response = alice.put(
        f"/api/scripts/{marked['script_ids'][0]}/decisions/{other_point}", json={"marks": 1}
    )
    assert response.status_code == 404


def test_accept_and_accept_all_copy_proposals_but_keep_teacher_decisions(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    p1, p2, p3 = (p["id"] for p in _points(_review(alice, script_id)))
    alice.put(f"/api/scripts/{script_id}/decisions/{p1}", json={"marks": 0, "category": "omitted"})
    review = alice.post(f"/api/scripts/{script_id}/decisions/{p2}/accept").json()
    assert (_points(review)[1]["final_marks"], _points(review)[1]["final_category"]) == (
        1,
        "correct",
    )

    body = alice.post(f"/api/scripts/{script_id}/accept-all").json()

    assert body["accepted"] == 1  # only p3 was still undecided
    finals = [(p["final_marks"], p["final_category"]) for p in _points(body["review"])]
    assert finals == [(0, "omitted"), (1, "correct"), (1, "correct")]
    assert body["review"]["can_confirm"] is True
    assert body["review"]["totals"]["final_total"] == 2
    assert [e.entity_id for e in _events(db, "accept")] == [_decision_id(db, script_id, p2)]
    assert [e.entity_id for e in _events(db, "accept_all")] == [_decision_id(db, script_id, p3)]


def _decision_id(db: Session, script_id: int, point_id: int) -> int:
    found = db.scalar(
        select(MarkDecision.id).where(
            MarkDecision.script_id == script_id, MarkDecision.mark_scheme_point_id == point_id
        )
    )
    assert found is not None
    return found


def test_question_total_is_capped_at_its_maximum(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    review = _review(alice, script_id)
    first_q = review["questions"][0]
    extra = MarkSchemePoint(
        question_id=first_q["id"], description="Shiny", half_marks=2, alternatives=[], position=99
    )
    db.add(extra)
    db.commit()
    alice.post(f"/api/scripts/{script_id}/accept-all")
    review = alice.put(f"/api/scripts/{script_id}/decisions/{extra.id}", json={"marks": 1}).json()
    assert review["questions"][0]["final_total"] == 2  # 3 awarded, capped at 2


# --- comments and transcriptions --------------------------------------------------------------


def test_comment_is_limited_to_300_characters_and_audited(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    question_id = _review(alice, script_id)["questions"][0]["id"]
    url = f"/api/scripts/{script_id}/questions/{question_id}/comment"

    too_long = alice.put(url, json={"text": "x" * 301})
    assert too_long.status_code == 422
    assert too_long.json()["code"] == "comment.too_long"
    review = alice.put(url, json={"text": "  Good use of terms.  "}).json()
    assert review["questions"][0]["comment"] == "Good use of terms."
    assert alice.put(url, json={"text": "y" * 300}).status_code == 200
    review = alice.put(url, json={"text": ""}).json()
    assert review["questions"][0]["comment"] == ""

    texts = [(e.old_value["text"], e.new_value["text"]) for e in _events(db, "set_comment")]
    assert texts == [("", "Good use of terms."), ("Good use of terms.", "y" * 300), ("y" * 300, "")]


def test_transcription_edit_adds_a_version_and_keeps_the_old_one(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    page = _answer_page(_review(alice, script_id))
    old_text = page["transcription"]["text"]

    review = alice.post(
        f"/api/pages/{page['id']}/transcription", json={"text": "1(a) corrected text"}
    ).json()

    page = _answer_page(review)
    assert page["transcription"]["text"] == "1(a) corrected text"
    assert page["transcription"]["source"] == "teacher"
    assert [v["text"] for v in page["versions"]] == [old_text, "1(a) corrected text"]
    assert page["edited_after_marking"] is True
    assert review["marked_on_earlier_text"] is True
    event = _events(db, "edit_transcription")[0]
    assert (event.old_value["text"], event.new_value["text"]) == (old_text, "1(a) corrected text")
    # Saving the same text again adds nothing.
    alice.post(f"/api/pages/{page['id']}/transcription", json={"text": "1(a) corrected text"})
    assert (
        len(db.scalars(select(Transcription).where(Transcription.page_id == page["id"])).all()) == 2
    )


def test_cover_pages_cannot_be_given_a_transcription(
    alice: ApiUser, marked: dict[str, Any]
) -> None:
    cover = next(p for p in _review(alice, marked["script_ids"][0])["pages"] if p["is_cover"])
    response = alice.post(f"/api/pages/{cover['id']}/transcription", json={"text": "x"})
    assert response.status_code == 409
    assert response.json()["code"] == "page.is_cover"


# --- orientation (layers a and c) -------------------------------------------------------------


def test_rotation_is_stored_audited_and_leaves_the_image_unchanged(
    alice: ApiUser, marked: dict[str, Any], db: Session, settings: Any
) -> None:
    page_id = _answer_page(_review(alice, marked["script_ids"][0]))["id"]
    row = db.get_one(Page, page_id)
    image = settings.data_dir / row.image_path
    before = hashlib.sha256(image.read_bytes()).hexdigest()

    review = alice.post(f"/api/pages/{page_id}/rotation", json={"rotation": 90}).json()

    page = _answer_page(review)
    assert (page["rotation"], page["rotation_teacher"]) == (90, 90)
    assert page["rotated_after_transcription"] is True
    assert hashlib.sha256(image.read_bytes()).hexdigest() == before
    review = alice.post(f"/api/pages/{page_id}/rotation", json={"rotation": None}).json()
    assert _answer_page(review)["rotation"] == 0
    events = _events(db, "rotate")
    assert [(e.old_value["rotation"], e.new_value["rotation"]) for e in events] == [
        (0, 90),
        (90, 0),
    ]
    assert alice.post(f"/api/pages/{page_id}/rotation", json={"rotation": 45}).status_code == 422


def test_undo_auto_rotation_restores_the_page_and_is_audited(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    page_id = _answer_page(_review(alice, marked["script_ids"][0]))["id"]
    row = db.get_one(Page, page_id)
    row.rotation_auto, row.auto_rotation_confidence = 180, 0.9
    db.commit()
    page = _answer_page(_review(alice, marked["script_ids"][0]))
    assert (page["auto_rotated"], page["rotation"], page["auto_rotation_confidence"]) == (
        True,
        180,
        0.9,
    )
    item = alice.get(f"/api/exams/{marked['exam_id']}/queue").json()["items"][0]
    assert item["auto_rotated_pages"] == 1

    review = alice.post(f"/api/pages/{page_id}/undo-auto-rotation").json()

    page = _answer_page(review)
    assert (page["auto_rotated"], page["rotation"]) == (False, 0)
    assert page["rotated_after_transcription"] is True
    event = _events(db, "undo_auto_rotation")[0]
    assert (event.old_value["rotation"], event.new_value["rotation"]) == (180, 0)
    again = alice.post(f"/api/pages/{page_id}/undo-auto-rotation")
    assert again.status_code == 409
    assert again.json()["code"] == "page.not_auto_rotated"


def test_teacher_rotation_overrides_the_automatic_one(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    page_id = _answer_page(_review(alice, marked["script_ids"][0]))["id"]
    row = db.get_one(Page, page_id)
    row.rotation_stack, row.rotation_auto = 90, 180
    db.commit()
    assert _answer_page(_review(alice, marked["script_ids"][0]))["rotation"] == 270
    review = alice.post(f"/api/pages/{page_id}/rotation", json={"rotation": 0}).json()
    assert (_answer_page(review)["rotation"], _answer_page(review)["auto_rotated"]) == (0, False)


def test_fresh_read_after_rotation_is_queued_on_request_only(
    app: FastAPI, alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    page_id = _answer_page(_review(alice, marked["script_ids"][0]))["id"]
    alice.post(f"/api/pages/{page_id}/rotation", json={"rotation": 180})
    run_jobs(app)  # nothing is re-read automatically
    assert len(db.scalars(select(Transcription).where(Transcription.page_id == page_id)).all()) == 1

    response = alice.post(f"/api/pages/{page_id}/retranscribe")
    assert response.status_code == 202
    assert _answer_page(response.json())["retranscribe_pending"] is True
    run_jobs(app)

    page = _answer_page(_review(alice, marked["script_ids"][0]))
    assert [v["rotation"] for v in page["versions"]] == [0, 180]
    assert page["transcription"]["rotation"] == 180
    assert page["rotated_after_transcription"] is False
    assert page["retranscribe_pending"] is False
    assert _events(db, "request_transcription")[0].new_value == {"rotation": 180}


# --- confirm, reopen, locking -----------------------------------------------------------------


def test_confirm_requires_every_point_decided(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    first = _points(_review(alice, script_id))[0]["id"]
    alice.post(f"/api/scripts/{script_id}/decisions/{first}/accept")

    response = alice.post(f"/api/scripts/{script_id}/confirm")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "script.incomplete"
    assert len(body["issues"]) == 2
    assert {i["code"] for i in body["issues"]} == {"script.point_undecided"}
    assert db.get_one(Script, script_id).status == ScriptStatus.IN_REVIEW


def test_confirm_locks_the_script_until_reopened(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    alice.post(f"/api/scripts/{script_id}/accept-all")
    review = alice.post(f"/api/scripts/{script_id}/confirm").json()
    assert review["locked"] is True
    assert review["script"]["status"] == "confirmed"
    script = db.get_one(Script, script_id)
    assert script.confirmed_by_id is not None
    assert script.confirmed_at is not None

    review_data = _review(alice, script_id)
    point_id = _points(review_data)[0]["id"]
    page_id = _answer_page(review_data)["id"]
    question_id = review_data["questions"][0]["id"]
    refused = [
        alice.put(f"/api/scripts/{script_id}/decisions/{point_id}", json={"marks": 0}),
        alice.post(f"/api/scripts/{script_id}/decisions/{point_id}/accept"),
        alice.post(f"/api/scripts/{script_id}/accept-all"),
        alice.put(f"/api/scripts/{script_id}/questions/{question_id}/comment", json={"text": "x"}),
        alice.post(f"/api/pages/{page_id}/transcription", json={"text": "x"}),
        alice.post(f"/api/pages/{page_id}/rotation", json={"rotation": 90}),
        alice.post(f"/api/pages/{page_id}/retranscribe"),
        alice.post(f"/api/scripts/{script_id}/confirm"),
    ]
    assert [(r.status_code, r.json()["code"]) for r in refused] == [(409, "script.confirmed")] * 8

    review = alice.post(f"/api/scripts/{script_id}/reopen").json()
    assert review["locked"] is False
    assert review["script"]["status"] == "in_review"
    assert (
        alice.put(f"/api/scripts/{script_id}/decisions/{point_id}", json={"marks": 0}).status_code
        == 200
    )
    again = alice.post(f"/api/scripts/{script_id}/reopen")
    assert again.status_code == 409
    assert again.json()["code"] == "script.not_confirmed"
    reopen = _events(db, "reopen")[0]
    assert reopen.old_value["status"] == "confirmed"
    assert reopen.new_value == {"status": "in_review"}


def test_scripts_still_being_marked_cannot_be_edited(
    alice: ApiUser, world: World, factory: Factory
) -> None:
    exam_id = _scan_exam(alice, world, factory, ("AAAAAA",))
    script_id = alice.get(f"/api/exams/{exam_id}/queue").json()["items"][0]["script_id"]
    review = _review(alice, script_id)
    assert review["ready"] is False
    point_id = _points(review)[0]["id"]
    response = alice.put(f"/api/scripts/{script_id}/decisions/{point_id}", json={"marks": 1})
    assert response.status_code == 409
    assert response.json()["code"] == "script.not_ready"


def test_manual_marking_script_is_marked_entirely_by_the_teacher(
    app: FastAPI,
    alice: ApiUser,
    world: World,
    factory: Factory,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenReader(MockReader):
        def transcribe(self, pages, subject):  # type: ignore[no-untyped-def]
            raise ModelOutputInvalidError("reader_schema")

    monkeypatch.setattr("app.worker.handlers.build_reader", lambda _s: BrokenReader())
    exam_id = _scan_exam(alice, world, factory, ("AAAAAA",))
    start_ai(alice, exam_id)
    run_jobs(app)
    item = alice.get(f"/api/exams/{exam_id}/queue").json()["items"][0]
    assert item["manual_reason"] == "ai.reader_invalid_output"
    assert item["reviewable"] is True
    script_id = item["script_id"]

    review = _review(alice, script_id)
    assert all(p["proposed_marks"] is None and p["decision_id"] is None for p in _points(review))
    assert _answer_page(review)["transcription"] is None
    accept = alice.post(f"/api/scripts/{script_id}/decisions/{_points(review)[0]['id']}/accept")
    assert accept.status_code == 409
    assert accept.json()["code"] == "decision.no_proposal"
    assert alice.post(f"/api/scripts/{script_id}/accept-all").json()["accepted"] == 0

    alice.post(
        f"/api/pages/{_answer_page(review)['id']}/transcription", json={"text": "typed by teacher"}
    )
    p1, p2, p3 = (p["id"] for p in _points(review))
    alice.put(f"/api/scripts/{script_id}/decisions/{p1}", json={"marks": 1})
    alice.put(f"/api/scripts/{script_id}/decisions/{p2}", json={"marks": 0})
    review = alice.put(f"/api/scripts/{script_id}/decisions/{p3}", json={"marks": 1}).json()
    # Full marks default to "correct"; anything else needs the teacher's category.
    assert [p["final_category"] for p in _points(review)] == ["correct", None, "correct"]
    assert review["can_confirm"] is False
    alice.put(f"/api/scripts/{script_id}/decisions/{p2}", json={"category": "omitted"})
    review = alice.post(f"/api/scripts/{script_id}/confirm").json()
    assert review["script"]["status"] == "confirmed"
    assert review["totals"]["final_total"] == 2
    rows = db.scalars(select(MarkDecision).where(MarkDecision.script_id == script_id)).all()
    assert len(rows) == 3
    assert all(r.model_name is None for r in rows)


# --- every edit is audited --------------------------------------------------------------------


def test_every_review_action_writes_exactly_one_audit_event(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    review = _review(alice, script_id)
    p1, p2, _p3 = (p["id"] for p in _points(review))
    page_id = _answer_page(review)["id"]
    question_id = review["questions"][0]["id"]
    row = db.get_one(Page, page_id)
    row.rotation_auto = 180
    db.commit()
    start = len(_events(db))

    alice.put(f"/api/scripts/{script_id}/decisions/{p1}", json={"marks": 0})
    alice.post(f"/api/scripts/{script_id}/decisions/{p2}/accept")
    alice.post(f"/api/scripts/{script_id}/accept-all")
    alice.put(f"/api/scripts/{script_id}/questions/{question_id}/comment", json={"text": "ok"})
    alice.post(f"/api/pages/{page_id}/transcription", json={"text": "new text"})
    alice.post(f"/api/pages/{page_id}/undo-auto-rotation")
    alice.post(f"/api/pages/{page_id}/rotation", json={"rotation": 90})
    alice.post(f"/api/pages/{page_id}/retranscribe")
    alice.post(f"/api/scripts/{script_id}/confirm")
    alice.post(f"/api/scripts/{script_id}/reopen")

    events = _events(db)[start:]
    assert [(e.action, e.entity_type) for e in events] == [
        ("set_decision", "mark_decision"),
        ("accept", "mark_decision"),
        ("accept_all", "mark_decision"),
        ("set_comment", "question_comment"),
        ("edit_transcription", "page"),
        ("undo_auto_rotation", "page"),
        ("rotate", "page"),
        ("request_transcription", "page"),
        ("confirm", "script"),
        ("reopen", "script"),
    ]
    user_id = db.scalar(select(Script.confirmed_by_id).where(Script.id == script_id))
    assert user_id is None  # reopened
    assert all(e.actor_id is not None for e in events)
    assert all(e.new_value is not None for e in events)
    # Reading the review or the queue writes nothing.
    _review(alice, script_id)
    alice.get(f"/api/exams/{marked['exam_id']}/queue")
    assert len(_events(db)) == start + len(events)


# --- review time (owner change 2) -------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def test_review_time_counts_from_opening_to_confirming_with_capped_active_time(
    alice: ApiUser, marked: dict[str, Any], db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    monkeypatch.setattr("app.services.review.utcnow", clock)
    script_id = marked["script_ids"][0]

    assert alice.post(f"/api/scripts/{script_id}/review-heartbeat").json() == {
        "session_open": True,
        "active_seconds": 0.0,
    }
    clock.advance(30)
    alice.post(f"/api/scripts/{script_id}/review-heartbeat")  # +30
    clock.advance(90)
    alice.post(f"/api/scripts/{script_id}/review-heartbeat")  # +60 (capped)
    clock.advance(600)
    alice.post(f"/api/scripts/{script_id}/review-heartbeat")  # idle gap: +0
    clock.advance(20)
    body = alice.post(f"/api/scripts/{script_id}/review-heartbeat").json()  # +20
    assert body["active_seconds"] == 110.0
    alice.post(f"/api/scripts/{script_id}/accept-all")
    clock.advance(10)
    alice.post(f"/api/scripts/{script_id}/confirm")  # +10 since the last heartbeat

    session = db.scalars(select(ReviewSession)).one()
    assert session.confirmed_at is not None
    assert (session.confirmed_at - session.opened_at).total_seconds() == 750
    assert session.active_seconds == 120.0
    queue = alice.get(f"/api/exams/{marked['exam_id']}/queue").json()
    item = next(i for i in queue["items"] if i["script_id"] == script_id)
    assert (item["review_seconds"], item["active_seconds"]) == (750, 120)
    assert (queue["average_review_seconds"], queue["average_active_seconds"]) == (750, 120)
    assert queue["timed_count"] == 1

    # A confirmed script being viewed is not review time.
    assert alice.post(f"/api/scripts/{script_id}/review-heartbeat").json()["session_open"] is False


def test_reopening_starts_a_new_session_and_times_add_up(
    alice: ApiUser, marked: dict[str, Any], db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    monkeypatch.setattr("app.services.review.utcnow", clock)
    first, second = marked["script_ids"]
    for script_id, seconds in ((first, 100), (second, 300)):
        alice.post(f"/api/scripts/{script_id}/review-heartbeat")
        alice.post(f"/api/scripts/{script_id}/accept-all")
        clock.advance(seconds)
        alice.post(f"/api/scripts/{script_id}/confirm")
    alice.post(f"/api/scripts/{first}/reopen")
    alice.post(f"/api/scripts/{first}/review-heartbeat")
    clock.advance(40)
    alice.post(f"/api/scripts/{first}/review-heartbeat")
    alice.post(f"/api/scripts/{first}/confirm")

    assert len(db.scalars(select(ReviewSession)).all()) == 3
    queue = alice.get(f"/api/exams/{marked['exam_id']}/queue").json()
    times = {i["script_id"]: (i["review_seconds"], i["active_seconds"]) for i in queue["items"]}
    # Confirming adds the time since the last heartbeat, capped at 60 s: first 60 + 40, second 60.
    assert times[first] == (140, 100)
    assert times[second] == (300, 60)
    assert queue["average_review_seconds"] == 220


# --- queue order --------------------------------------------------------------------------------


def _item(code: str, **overrides: Any) -> QueueItemOut:
    values: dict[str, Any] = {
        "script_id": 1,
        "student_code": code,
        "student_name": None,
        "status": ScriptStatus.AI_MARKED,
        "manual_reason": None,
        "reviewable": True,
        "page_count": 3,
        "page_count_flag": None,
        "auto_rotated_pages": 0,
        "min_confidence": 0.9,
        "uncertain_points": 0,
        "deductions": 0,
        "marks_deducted": 0,
        "decided_points": 0,
        "total_points": 3,
        "proposed_total": 3,
        "final_total": None,
        "max_total": 3,
        "review_seconds": None,
        "active_seconds": None,
        "test_model": False,
    }
    values.update(overrides)
    return QueueItemOut(**values)


def test_queue_puts_the_most_uncertain_scripts_first() -> None:
    items = [
        _item("CONFIRMED", status=ScriptStatus.CONFIRMED, manual_reason="ai.x"),
        _item("PLAIN"),
        _item("WAITING", status=ScriptStatus.WAITING, reviewable=False, min_confidence=None),
        _item("PAGEFLAG", page_count_flag="more_than_usual"),
        _item("LOWCONF", min_confidence=0.3),
        _item("UNCERTAIN", uncertain_points=1, min_confidence=0.95),
        _item("MANUAL", manual_reason="ai.marker_invalid_output", min_confidence=None),
    ]
    order = [i.student_code for i in sorted(items, key=_queue_order)]
    assert order == ["MANUAL", "UNCERTAIN", "LOWCONF", "PAGEFLAG", "PLAIN", "WAITING", "CONFIRMED"]


# --- export guard -----------------------------------------------------------------------------


def test_unconfirmed_scripts_cannot_be_exported(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    exam = db.get_one(Exam, marked["exam_id"])
    first, second = (db.get_one(Script, i) for i in marked["script_ids"])
    assert exports.exportable_scripts(db, exam) == []
    with pytest.raises(ConflictError) as raised:
        exports.require_confirmed(first)
    assert raised.value.code == "export.not_confirmed"

    alice.post(f"/api/scripts/{first.id}/accept-all")
    alice.post(f"/api/scripts/{first.id}/confirm")
    db.expire_all()
    assert exports.exportable_scripts(db, exam) == [first]
    exports.require_confirmed(first)
    with pytest.raises(ConflictError):
        exports.require_confirmed(second)
    alice.post(f"/api/scripts/{first.id}/reopen")
    db.expire_all()
    assert exports.exportable_scripts(db, exam) == []


# --- permissions --------------------------------------------------------------------------------


def test_another_teacher_gets_not_found_on_every_review_endpoint(
    alice: ApiUser, bruno: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    script_id = marked["script_ids"][0]
    review = _review(alice, script_id)
    point_id = _points(review)[0]["id"]
    page_id = _answer_page(review)["id"]
    question_id = review["questions"][0]["id"]
    responses = [
        bruno.get(f"/api/exams/{marked['exam_id']}/queue"),
        bruno.get(f"/api/scripts/{script_id}/review"),
        bruno.post(f"/api/scripts/{script_id}/review-heartbeat"),
        bruno.put(f"/api/scripts/{script_id}/decisions/{point_id}", json={"marks": 0}),
        bruno.post(f"/api/scripts/{script_id}/decisions/{point_id}/accept"),
        bruno.post(f"/api/scripts/{script_id}/accept-all"),
        bruno.put(f"/api/scripts/{script_id}/questions/{question_id}/comment", json={"text": "x"}),
        bruno.post(f"/api/scripts/{script_id}/confirm"),
        bruno.post(f"/api/scripts/{script_id}/reopen"),
        bruno.post(f"/api/pages/{page_id}/transcription", json={"text": "x"}),
        bruno.post(f"/api/pages/{page_id}/rotation", json={"rotation": 90}),
        bruno.post(f"/api/pages/{page_id}/undo-auto-rotation"),
        bruno.post(f"/api/pages/{page_id}/retranscribe"),
    ]
    assert [r.status_code for r in responses] == [404] * len(responses)
    assert db.scalars(select(ReviewSession)).all() == []
