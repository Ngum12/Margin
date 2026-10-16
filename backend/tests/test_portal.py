"""Student isolation, explicit release, PIN lifecycle and audited post-release changes."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db.models import AuditEvent, Exam, Role, Script, Student
from app.db.models.portal import StudentSession
from app.services import student_auth
from tests.conftest import World
from tests.factories import ApiUser, Factory, run_jobs, start_ai
from tests.test_review import _scan_exam


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def marked(app: FastAPI, alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    exam_id = _scan_exam(alice, world, factory, ("AAAAAA", "BBBBBB"))
    start_ai(alice, exam_id)
    run_jobs(app)
    queue = alice.get(f"/api/exams/{exam_id}/queue").json()
    return {"exam_id": exam_id, "script_ids": [item["script_id"] for item in queue["items"]]}


@pytest.fixture
def portal_data(
    app: FastAPI, db: Session, world: World, marked: dict[str, Any], alice: ApiUser
) -> dict[str, Any]:
    world.school.portal_settings = {"enabled": True, "escalation": True}
    db.commit()
    pins = {}
    for student in db.scalars(select(Student).where(Student.class_id == world.class_a.id)):
        _, pin = student_auth.issue(db, world.teacher_a, student.id, reset=False)
        pins[student.code] = pin
    db.commit()
    for script_id in marked["script_ids"]:
        assert alice.post(f"/api/scripts/{script_id}/accept-all").status_code == 200
        assert alice.post(f"/api/scripts/{script_id}/confirm").status_code == 200
    return {**marked, "pins": pins, "school_id": world.school.id}


def sign_in(
    app: FastAPI, data: dict[str, Any], code: str = "AAAAAA", *, change: bool = True
) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post(
        "/api/student/login",
        json={"school_id": data["school_id"], "code": code, "pin": data["pins"][code]},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    if change:
        response = client.put(
            "/api/student/pin",
            json={"old_pin": data["pins"][code], "pin": "72519384"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200, response.text
    return client, csrf


def publish(alice: ApiUser, data: dict[str, Any], visibility: str = "notes") -> None:
    result = alice.put(
        f"/api/exams/{data['exam_id']}/release", json={"released": True, "visibility": visibility}
    )
    assert result.status_code == 200, result.text


def test_student_pin_release_images_and_staff_isolation(
    app: FastAPI, db: Session, portal_data: dict[str, Any], alice: ApiUser
) -> None:
    client, csrf = sign_in(app, portal_data, change=False)
    assert client.get("/api/student/exams").status_code == 403
    assert (
        client.put(
            "/api/student/pin", json={"old_pin": portal_data["pins"]["AAAAAA"], "pin": "72519384"}
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/student/pin",
            json={"old_pin": portal_data["pins"]["AAAAAA"], "pin": "72519384"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 200
    )
    assert client.get("/api/student/exams").json() == []
    for route in (
        "/api/classes",
        "/api/remarks",
        "/api/portal/settings",
        "/api/users",
        "/api/auth/me",
    ):
        assert client.get(route).status_code == 401
    publish(alice, portal_data)
    exams = client.get("/api/student/exams").json()
    assert len(exams) == 1
    own = exams[0]
    assert own["total"] == 3
    assert not any(q["scheme"] for q in own["questions"])
    page_id = own["pages"][0]["id"]
    image = client.get(f"/api/student/pages/{page_id}/image")
    assert image.status_code == 200
    assert image.content.startswith(b"\xff\xd8")
    assert image.headers["cache-control"] == "no-store"
    assert image.headers["content-type"] == "image/jpeg"
    other = next(s for s in db.scalars(select(Script)) if s.id != own["id"])
    assert client.get(f"/api/student/scripts/{other.id}").status_code == 404
    assert client.get(f"/api/student/scripts/{other.id}/marks").status_code == 404
    assert client.get(f"/api/student/pages/{other.pages[-1].id}/image").status_code == 404
    assert client.get(f"/api/scripts/{own['id']}/review").status_code == 401
    publish(alice, portal_data, "scheme")
    assert client.get(f"/api/student/scripts/{own['id']}").json()["questions"][0]["scheme"]
    publish(alice, portal_data, "marks")
    body = client.get(f"/api/student/scripts/{own['id']}").json()
    assert all(
        not q["scheme"] and not q["feedback"] and not q["comment"] for q in body["questions"]
    )
    assert (
        alice.put(
            f"/api/exams/{portal_data['exam_id']}/release", json={"released": False}
        ).status_code
        == 200
    )
    assert client.get(f"/api/student/pages/{page_id}/image").status_code == 404


def test_remark_reply_updates_released_totals_and_escalation_scope(
    app: FastAPI,
    db: Session,
    world: World,
    factory: Factory,
    portal_data: dict[str, Any],
    alice: ApiUser,
) -> None:
    client, csrf = sign_in(app, portal_data)
    publish(alice, portal_data)
    own = client.get("/api/student/exams").json()[0]
    question = own["questions"][0]
    body = {
        "question_id": question["id"],
        "reason": "missing_mark",
        "message": "Please check this answer.",
    }
    headers = {"X-CSRF-Token": csrf}
    response = client.post(f"/api/student/scripts/{own['id']}/remarks", json=body, headers=headers)
    assert response.status_code == 200, response.text
    ident = response.json()["id"]
    assert (
        client.post(
            f"/api/student/scripts/{own['id']}/remarks", json=body, headers=headers
        ).status_code
        == 409
    )
    bruno = ApiUser(app, "bruno")
    assert bruno.post(f"/api/remarks/{ident}/reply", json={"message": "no"}).status_code == 404
    review = alice.get(f"/api/scripts/{own['id']}/review").json()
    point = review["questions"][0]["points"][0]["id"]
    response = alice.post(
        f"/api/remarks/{ident}/reply",
        json={"message": "This point was credited in error.", "marks": {str(point): 0}},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/student/scripts/{own['id']}").json()["total"] == 2
    db.expire_all()
    assert db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "set_decision",
            AuditEvent.reason == "This point was credited in error.",
        )
    )
    assert client.post(f"/api/student/remarks/{ident}/escalate", headers=headers).status_code == 200
    assert alice.post(f"/api/remarks/{ident}/reply", json={"message": "no"}).status_code == 403
    hod = factory.user(world.school, "head", Role.HEAD_OF_DEPARTMENT)
    hod.department_subject_codes = ["mathematics"]
    db.commit()
    head = ApiUser(app, "head")
    assert head.post(f"/api/remarks/{ident}/reply", json={"message": "no"}).status_code == 404
    hod.department_subject_codes = ["chemistry"]
    db.commit()
    assert (
        head.post(
            f"/api/remarks/{ident}/reply", json={"message": "Department review completed."}
        ).status_code
        == 200
    )
    assert client.post(f"/api/student/remarks/{ident}/escalate", headers=headers).status_code == 409
    assert alice.post(f"/api/scripts/{own['id']}/reopen").status_code == 409


def test_remark_limits_window_and_automatic_total(
    app: FastAPI, db: Session, world: World, portal_data: dict[str, Any], alice: ApiUser
) -> None:
    client, csrf = sign_in(app, portal_data)
    publish(alice, portal_data)
    own = client.get("/api/student/exams").json()[0]
    headers = {"X-CSRF-Token": csrf}
    response = client.post(
        f"/api/student/scripts/{own['id']}/remarks",
        json={
            "question_id": own["questions"][0]["id"],
            "reason": "total_error",
            "message": "Is this total correct?",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "answered"
    assert response.json()["responses"][0]["total"] == 3
    world.school.portal_settings = {"enabled": True, "remark_max": 1}
    db.commit()
    data = {"question_id": own["questions"][1]["id"], "reason": "other", "message": "Check please"}
    assert (
        client.post(f"/api/student/scripts/{own['id']}/remarks", json=data, headers=headers).json()[
            "code"
        ]
        == "portal.remark_limit"
    )
    exam = db.get(Exam, portal_data["exam_id"])
    assert exam
    exam.released_at = utcnow() - timedelta(days=8)
    db.commit()
    assert (
        client.post(f"/api/student/scripts/{own['id']}/remarks", json=data, headers=headers).json()[
            "code"
        ]
        == "portal.remark_closed"
    )


def test_session_timeout_reset_portal_off_and_persistent_lockout(
    app: FastAPI, db: Session, world: World, portal_data: dict[str, Any]
) -> None:
    client, _csrf = sign_in(app, portal_data)
    session = db.scalar(select(StudentSession))
    assert session
    session.last_seen_at = utcnow() - timedelta(minutes=11)
    db.commit()
    assert client.get("/api/student/me").status_code == 401
    student = db.scalar(select(Student).where(Student.code == "AAAAAA"))
    assert student
    _, pin = student_auth.issue(db, world.teacher_a, student.id, reset=True)
    db.commit()
    assert client.get("/api/student/me").status_code == 401
    attempt = {"school_id": world.school.id, "code": student.code, "pin": "wrong"}
    for _ in range(5):
        assert client.post("/api/student/login", json=attempt).status_code == 401
    assert client.post("/api/student/login", json={**attempt, "pin": pin}).status_code == 429
    other, _ = sign_in(app, portal_data, "BBBBBB")
    world.school.portal_settings = {"enabled": False}
    db.commit()
    assert other.get("/api/student/exams").status_code == 401


def test_public_hostname_rejects_staff_paths(app: FastAPI, world: World) -> None:
    from app.student_host import StudentHostMiddleware

    client = TestClient(
        StudentHostMiddleware(app, "students.example"), base_url="https://students.example"
    )
    for path in (
        "/api/classes",
        "/api/auth/login",
        "/settings",
        "/api/student/../classes",
        "/api/student/%252e%252e/classes",
    ):
        assert client.get(path).status_code == 404
    assert client.get("/api/student/schools").status_code == 200


def test_credential_slips_private_idempotent_and_last_admin_protected(
    app: FastAPI, world: World, factory: Factory, db: Session
) -> None:
    student = factory.student(world.class_a, "CCCCCC")
    alice = ApiUser(app, "alice")
    data = {"student_ids": [student.id], "key": "one-request-key-12345"}
    first = alice.post("/api/portal/credentials", json=data)
    assert first.status_code == 200, first.text
    second = alice.post("/api/portal/credentials", json=data)
    assert second.json()["id"] == first.json()["id"]
    url = f"/api/portal/credentials/{first.json()['id']}.pdf"
    assert alice.get(url).content.startswith(b"%PDF-")
    assert ApiUser(app, "bruno").get(url).status_code == 404
    assert TestClient(app).get(url).status_code == 401
    admin = ApiUser(app, "admin")
    assert (
        admin.patch(f"/api/users/{world.admin.id}", json={"role": "head_of_department"}).json()[
            "code"
        ]
        == "user.last_admin"
    )
    # No credentials or hashes appear in the audit trail.
    events = list(
        db.scalars(
            select(AuditEvent).where(AuditEvent.action.in_(["issue_pin", "print_credentials"]))
        )
    )
    assert events
    assert all("pin_hash" not in str(e.new_value) for e in events)


def test_release_waits_for_whole_class_and_student_cookie_is_not_staff_cookie(
    app: FastAPI,
    db: Session,
    world: World,
    factory: Factory,
    portal_data: dict[str, Any],
    alice: ApiUser,
) -> None:
    factory.student(world.class_a, "CCCCCC")  # Later enrolment does not change an old exam roster.
    pending = portal_data["script_ids"][1]
    assert alice.post(f"/api/scripts/{pending}/reopen").status_code == 200
    response = alice.put(f"/api/exams/{portal_data['exam_id']}/release", json={"released": True})
    assert response.status_code == 409
    assert alice.post(f"/api/scripts/{pending}/confirm").status_code == 200
    publish(alice, portal_data)
    client, _ = sign_in(app, portal_data)
    from app.auth.sessions import SESSION_COOKIE_NAME

    token = client.cookies.get(student_auth.COOKIE)
    assert token
    client.cookies.set(SESSION_COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401
