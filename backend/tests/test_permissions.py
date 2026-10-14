"""Permission boundaries: a teacher sees and changes only their own classes, students and exams.
Out-of-scope ids answer 404, exactly like ids that do not exist."""

from typing import Any

import pytest
from fastapi import FastAPI

from tests.conftest import World
from tests.factories import ApiUser, Factory, complete_scheme


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def bruno(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "bruno")


@pytest.fixture
def admin(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "admin")


def _create_exam(user: ApiUser, class_id: int, title: str = "Mock 1") -> dict[str, Any]:
    response = user.post(
        "/api/exams", json={"class_id": class_id, "subject_code": "chemistry", "title": title}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_teacher_cannot_read_another_teachers_exam(
    alice: ApiUser, bruno: ApiUser, world: World
) -> None:
    exam = _create_exam(alice, world.class_a.id)

    response = bruno.get(f"/api/exams/{exam['id']}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert response.json() == bruno.get("/api/exams/999999").json()


def test_teacher_exam_list_shows_only_own_exams(
    alice: ApiUser, bruno: ApiUser, world: World
) -> None:
    _create_exam(alice, world.class_a.id, "Alice exam")
    _create_exam(bruno, world.class_b.id, "Bruno exam")

    titles = [e["title"] for e in bruno.get("/api/exams").json()]

    assert titles == ["Bruno exam"]


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("patch", "", {"title": "Hijacked"}),
        ("put", "/mark-scheme", complete_scheme()),
        ("put", "/status", {"status": "ready"}),
        ("delete", "", None),
    ],
)
def test_teacher_cannot_change_another_teachers_exam(
    alice: ApiUser, bruno: ApiUser, world: World, method: str, suffix: str, body: Any
) -> None:
    exam = _create_exam(alice, world.class_a.id)
    url = f"/api/exams/{exam['id']}{suffix}"

    response = bruno.delete(url) if method == "delete" else getattr(bruno, method)(url, json=body)

    assert response.status_code == 404
    assert alice.get(f"/api/exams/{exam['id']}").json()["title"] == "Mock 1"


def test_teacher_cannot_create_exam_in_another_teachers_class(bruno: ApiUser, world: World) -> None:
    response = bruno.post(
        "/api/exams",
        json={"class_id": world.class_a.id, "subject_code": "chemistry", "title": "X"},
    )

    assert response.status_code == 404


def test_teacher_sees_only_own_classes(alice: ApiUser, world: World) -> None:
    classes = alice.get("/api/classes").json()

    assert [c["id"] for c in classes] == [world.class_a.id]


def test_teacher_cannot_list_another_classes_students(
    bruno: ApiUser, world: World, factory: Factory
) -> None:
    factory.student(world.class_a, "AAAAAA", "Real Name")

    response = bruno.get(f"/api/classes/{world.class_a.id}/students")

    assert response.status_code == 404
    assert "Real Name" not in response.text


def test_teacher_can_list_own_students(alice: ApiUser, world: World, factory: Factory) -> None:
    factory.student(world.class_a, "AAAAAA")

    response = alice.get(f"/api/classes/{world.class_a.id}/students")

    assert [s["code"] for s in response.json()] == ["AAAAAA"]


@pytest.mark.parametrize(
    ("method", "url_template", "body"),
    [
        ("get", "/api/users", None),
        ("post", "/api/users", {"username": "eve", "display_name": "Eve", "password": "x" * 12}),
        ("post", "/api/classes", {"name": "X", "academic_year": "2026/2027", "teacher_id": 1}),
        ("patch", "/api/classes/{class_a}", {"name": "Renamed"}),
        ("post", "/api/classes/{class_a}/students", {"names": ["New"]}),
    ],
)
def test_admin_only_actions_are_refused_for_teachers(
    alice: ApiUser, world: World, method: str, url_template: str, body: Any
) -> None:
    url = url_template.format(class_a=world.class_a.id)

    response = alice.get(url) if method == "get" else getattr(alice, method)(url, json=body)

    assert response.status_code == 403
    assert response.json()["code"] == "auth.admin_required"


def test_teacher_cannot_change_consent_even_for_own_student(
    alice: ApiUser, world: World, factory: Factory
) -> None:
    student = factory.student(world.class_a, "AAAAAA")

    response = alice.put(f"/api/students/{student.id}/consent", json={"training_consent": True})

    assert response.status_code == 403


def test_admin_sees_all_classes_and_exams(
    admin: ApiUser, alice: ApiUser, bruno: ApiUser, world: World
) -> None:
    _create_exam(alice, world.class_a.id, "A")
    _create_exam(bruno, world.class_b.id, "B")

    assert len(admin.get("/api/classes").json()) == 2
    assert sorted(e["title"] for e in admin.get("/api/exams").json()) == ["A", "B"]


def test_users_of_another_school_are_invisible(
    admin: ApiUser, factory: Factory, world: World
) -> None:
    other_school = factory.school()
    stranger = factory.user(other_school, "stranger")
    other_class = factory.school_class(other_school, stranger, "Elsewhere")

    assert "stranger" not in [u["username"] for u in admin.get("/api/users").json()]
    assert admin.get(f"/api/classes/{other_class.id}/students").status_code == 404
    assert admin.patch(f"/api/users/{stranger.id}", json={"display_name": "X"}).status_code == 404


def test_reassigning_a_class_moves_access_to_the_new_teacher(
    admin: ApiUser, alice: ApiUser, bruno: ApiUser, world: World
) -> None:
    exam = _create_exam(alice, world.class_a.id)

    admin.patch(f"/api/classes/{world.class_a.id}", json={"teacher_id": world.teacher_b.id})

    assert alice.get(f"/api/exams/{exam['id']}").status_code == 404
    assert bruno.get(f"/api/exams/{exam['id']}").status_code == 200
