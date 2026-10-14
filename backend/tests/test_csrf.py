from fastapi import FastAPI

from tests.conftest import World
from tests.factories import ApiUser


def _exam_body(world: World) -> dict[str, object]:
    return {"class_id": world.class_a.id, "subject_code": "chemistry", "title": "Mock 1"}


def test_unsafe_request_without_csrf_token_is_rejected(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    response = user.client.post("/api/exams", json=_exam_body(world))

    assert response.status_code == 403
    assert response.json()["code"] == "auth.csrf_failed"


def test_unsafe_request_with_wrong_csrf_token_is_rejected(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    response = user.client.post(
        "/api/exams", json=_exam_body(world), headers={"X-CSRF-Token": "forged"}
    )

    assert response.status_code == 403


def test_csrf_token_from_another_session_is_rejected(app: FastAPI, world: World) -> None:
    alice = ApiUser(app, "alice")
    other_alice = ApiUser(app, "alice")

    response = alice.client.post(
        "/api/exams", json=_exam_body(world), headers={"X-CSRF-Token": other_alice.csrf}
    )

    assert response.status_code == 403


def test_unsafe_request_with_csrf_token_succeeds(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    assert user.post("/api/exams", json=_exam_body(world)).status_code == 201


def test_logout_requires_csrf(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    assert user.client.post("/api/auth/logout").status_code == 403
    assert user.get("/api/auth/me").status_code == 200


def test_safe_requests_need_no_csrf_token(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    assert user.client.get("/api/exams").status_code == 200
