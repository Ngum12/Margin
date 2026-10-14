from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, MarkSchemePoint, Question, User
from tests.conftest import World
from tests.factories import ApiUser, complete_scheme


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def exam(alice: ApiUser, world: World) -> dict[str, Any]:
    response = alice.post(
        "/api/exams",
        json={
            "class_id": world.class_a.id,
            "subject_code": "chemistry",
            "title": "Mock exam 1",
            "exam_date": "2026-11-20",
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_new_exam_is_an_empty_draft(exam: dict[str, Any]) -> None:
    assert exam["status"] == "draft"
    assert exam["questions"] == []
    assert exam["total_marks"] == 0
    assert exam["class_name"] == "Form 5A"
    assert exam["scripts"] == {"waiting": 0, "ai_marked": 0, "confirmed": 0}
    assert exam["validation"]["is_ready"] is False
    assert [i["code"] for i in exam["validation"]["readiness"]] == ["exam.no_questions"]


def test_unknown_subject_is_rejected(alice: ApiUser, world: World) -> None:
    response = alice.post(
        "/api/exams",
        json={"class_id": world.class_a.id, "subject_code": "astrology", "title": "X"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "exam.subject_unknown"


def test_saving_a_mark_scheme_returns_it_with_totals(alice: ApiUser, exam: dict[str, Any]) -> None:
    response = alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())

    assert response.status_code == 200
    body = response.json()
    assert body["total_marks"] == 3
    assert body["question_count"] == 2
    assert [q["label"] for q in body["questions"]] == ["1(a)", "1(b)"]
    assert body["questions"][0]["points"][0]["alternatives"] == ["conductor"]
    assert body["validation"]["is_ready"] is True


def test_marks_are_stored_as_half_mark_units(
    alice: ApiUser, exam: dict[str, Any], db: Session
) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())

    question = db.scalars(select(Question).where(Question.label == "1(a)")).one()
    assert question.max_half_marks == 4
    assert [p.half_marks for p in question.points] == [2, 2]


def test_replacing_a_mark_scheme_removes_old_rows(
    alice: ApiUser, exam: dict[str, Any], db: Session
) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())
    smaller = complete_scheme()
    smaller["questions"] = smaller["questions"][1:]

    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=smaller)

    assert db.scalars(select(Question)).all()[0].label == "1(b)"
    assert len(db.scalars(select(MarkSchemePoint)).all()) == 1


def test_swapping_question_order_saves(alice: ApiUser, exam: dict[str, Any]) -> None:
    scheme = complete_scheme()
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=scheme)
    scheme["questions"].reverse()

    response = alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=scheme)

    assert [q["label"] for q in response.json()["questions"]] == ["1(b)", "1(a)"]


def test_blocking_errors_prevent_saving(alice: ApiUser, exam: dict[str, Any]) -> None:
    scheme = complete_scheme()
    scheme["questions"][1]["label"] = "1(A)"  # duplicate, case-insensitive

    response = alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=scheme)

    assert response.status_code == 422
    assert response.json()["code"] == "mark_scheme.invalid"
    issue = response.json()["issues"][0]
    assert issue["code"] == "question.label_duplicate"
    assert issue["path"] == ["questions", 1, "label"]


def test_incomplete_scheme_saves_as_draft_but_cannot_be_ready(
    alice: ApiUser, exam: dict[str, Any]
) -> None:
    scheme = complete_scheme()
    scheme["questions"][0]["max_marks"] = 3  # points only add up to 2

    saved = alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=scheme)
    ready = alice.put(f"/api/exams/{exam['id']}/status", json={"status": "ready"})

    assert saved.status_code == 200
    assert saved.json()["validation"]["readiness"][0]["code"] == "question.points_below_max"
    assert ready.status_code == 422
    assert ready.json()["code"] == "exam.not_ready"
    assert ready.json()["issues"][0]["params"] == {
        "label": "1(a)",
        "points_total": 2,
        "max_marks": 3,
    }


def test_complete_exam_can_be_marked_ready_and_back(alice: ApiUser, exam: dict[str, Any]) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())

    ready = alice.put(f"/api/exams/{exam['id']}/status", json={"status": "ready"})
    draft = alice.put(f"/api/exams/{exam['id']}/status", json={"status": "draft"})

    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert draft.json()["status"] == "draft"


def test_mark_scheme_is_locked_once_ready(alice: ApiUser, exam: dict[str, Any]) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())
    alice.put(f"/api/exams/{exam['id']}/status", json={"status": "ready"})

    response = alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())

    assert response.status_code == 409
    assert response.json()["code"] == "exam.not_draft"


def test_phase_one_does_not_allow_later_statuses(alice: ApiUser, exam: dict[str, Any]) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())
    alice.put(f"/api/exams/{exam['id']}/status", json={"status": "ready"})

    response = alice.put(f"/api/exams/{exam['id']}/status", json={"status": "completed"})

    assert response.status_code == 409
    assert response.json()["code"] == "exam.invalid_transition"


def test_details_can_be_edited_and_date_cleared(alice: ApiUser, exam: dict[str, Any]) -> None:
    response = alice.patch(f"/api/exams/{exam['id']}", json={"title": "Renamed", "exam_date": None})

    assert response.json()["title"] == "Renamed"
    assert response.json()["exam_date"] is None


def test_subject_is_locked_once_ready(alice: ApiUser, exam: dict[str, Any]) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())
    alice.put(f"/api/exams/{exam['id']}/status", json={"status": "ready"})

    response = alice.patch(f"/api/exams/{exam['id']}", json={"subject_code": "economics"})

    assert response.status_code == 409


def test_only_draft_exams_can_be_deleted(alice: ApiUser, exam: dict[str, Any]) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())
    alice.put(f"/api/exams/{exam['id']}/status", json={"status": "ready"})
    assert alice.delete(f"/api/exams/{exam['id']}").status_code == 409

    alice.put(f"/api/exams/{exam['id']}/status", json={"status": "draft"})
    assert alice.delete(f"/api/exams/{exam['id']}").status_code == 204
    assert alice.get(f"/api/exams/{exam['id']}").status_code == 404


def test_exam_changes_are_audited(alice: ApiUser, exam: dict[str, Any], db: Session) -> None:
    alice.put(f"/api/exams/{exam['id']}/mark-scheme", json=complete_scheme())
    alice.put(f"/api/exams/{exam['id']}/status", json={"status": "ready"})

    events = db.scalars(
        select(AuditEvent).where(AuditEvent.entity_type == "exam").order_by(AuditEvent.id)
    ).all()

    assert [e.action for e in events] == ["create", "replace_mark_scheme", "set_status"]
    assert all(e.actor_id == alice_id(db) for e in events)
    assert events[1].old_value == {"questions": []}
    assert events[1].new_value["questions"][0]["max_marks"] == 2
    assert (events[2].old_value, events[2].new_value) == ("draft", "ready")


def alice_id(db: Session) -> int:
    return db.scalars(select(User.id).where(User.username == "alice")).one()


def test_subjects_endpoint_lists_curriculum_subjects(alice: ApiUser) -> None:
    subjects = alice.get("/api/subjects").json()

    assert [s["code"] for s in subjects] == ["chemistry", "economics", "mathematics"]
    assert subjects[0]["name_fr"] == "Chimie"
