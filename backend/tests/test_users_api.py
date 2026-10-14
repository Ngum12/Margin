import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.db.models import AuditEvent, User
from tests.conftest import World
from tests.factories import ApiUser


@pytest.fixture
def admin(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "admin")


def test_admin_creates_a_teacher(admin: ApiUser, db: Session) -> None:
    response = admin.post(
        "/api/users",
        json={
            "username": " New.Teacher ",
            "display_name": "Mme Ndi",
            "password": "a-long-password",
            "preferred_language": "fr",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "new.teacher"
    assert body["role"] == "teacher"
    user = db.scalars(select(User).where(User.username == "new.teacher")).one()
    assert verify_password(user.password_hash, "a-long-password")


def test_new_user_can_sign_in(admin: ApiUser, app: FastAPI) -> None:
    admin.post(
        "/api/users",
        json={"username": "ndi", "display_name": "Ndi", "password": "a-long-password"},
    )

    assert ApiUser(app, "ndi", "a-long-password").get("/api/auth/me").status_code == 200


def test_duplicate_username_conflicts(admin: ApiUser) -> None:
    response = admin.post(
        "/api/users", json={"username": "ALICE", "display_name": "A", "password": "a-long-password"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "user.username_taken"


def test_short_password_is_rejected(admin: ApiUser) -> None:
    response = admin.post(
        "/api/users", json={"username": "short", "display_name": "S", "password": "short"}
    )

    assert response.status_code == 422


def test_passwords_never_reach_the_audit_log(admin: ApiUser, db: Session, world: World) -> None:
    admin.post(
        "/api/users",
        json={"username": "ndi", "display_name": "Ndi", "password": "a-long-password"},
    )
    admin.post(f"/api/users/{world.teacher_a.id}/password", json={"password": "another-password"})

    dump = str([(e.old_value, e.new_value) for e in db.scalars(select(AuditEvent))])
    assert "a-long-password" not in dump
    assert "another-password" not in dump
    assert "argon2" not in dump


def test_reset_password_signs_the_user_out(admin: ApiUser, app: FastAPI, world: World) -> None:
    alice = ApiUser(app, "alice")

    admin.post(f"/api/users/{world.teacher_a.id}/password", json={"password": "another-password"})

    assert alice.get("/api/auth/me").status_code == 401
    assert ApiUser(app, "alice", "another-password").get("/api/auth/me").status_code == 200


def test_deactivating_a_user_signs_them_out(admin: ApiUser, app: FastAPI, world: World) -> None:
    alice = ApiUser(app, "alice")

    admin.patch(f"/api/users/{world.teacher_a.id}", json={"is_active": False})

    assert alice.get("/api/auth/me").status_code == 401


def test_last_admin_cannot_be_demoted_or_deactivated(admin: ApiUser, world: World) -> None:
    demote = admin.patch(f"/api/users/{world.admin.id}", json={"role": "teacher"})

    assert demote.status_code == 409
    assert demote.json()["code"] == "user.last_admin"


def test_admin_cannot_deactivate_self_even_with_another_admin(admin: ApiUser, world: World) -> None:
    admin.patch(f"/api/users/{world.teacher_b.id}", json={"role": "admin"})

    response = admin.patch(f"/api/users/{world.admin.id}", json={"is_active": False})

    assert response.json()["code"] == "user.cannot_deactivate_self"


def test_null_fields_leave_values_unchanged(admin: ApiUser, world: World) -> None:
    response = admin.patch(
        f"/api/users/{world.teacher_a.id}", json={"role": None, "display_name": None}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "teacher"
    assert response.json()["display_name"] == "Alice"
