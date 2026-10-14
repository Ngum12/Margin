import logging
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.sessions import SESSION_COOKIE_NAME
from app.config import Settings
from app.db.base import Base
from app.db.models import LoginAttempt, UserSession
from app.main import create_app
from tests.conftest import World
from tests.factories import PASSWORD, ApiUser, Factory


def _login(
    client: TestClient, username: str, password: str = PASSWORD, **headers: str
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/auth/login", json={"username": username, "password": password}, headers=headers
    )
    return response


def test_login_sets_httponly_lax_cookie_and_returns_csrf(client: TestClient, world: World) -> None:
    response = _login(client, "alice")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "alice"
    assert body["user"]["role"] == "teacher"
    assert body["school"]["curriculum"] == "cm_gce_ol"
    assert len(body["csrf_token"]) >= 32
    assert "password_hash" not in body["user"]
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie  # test env: secure cookies off


def test_username_is_case_insensitive(client: TestClient, world: World) -> None:
    assert _login(client, "  ALICE ").status_code == 200


def test_me_requires_session(client: TestClient, world: World) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.required"


def test_me_returns_user_after_login(client: TestClient, world: World) -> None:
    csrf = _login(client, "alice").json()["csrf_token"]

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["csrf_token"] == csrf


def test_wrong_password_and_unknown_user_get_the_same_answer(
    client: TestClient, world: World
) -> None:
    wrong = _login(client, "alice", "not-the-password")
    unknown = _login(client, "nobody", "not-the-password")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "auth.invalid_credentials"
    assert "set-cookie" not in wrong.headers


def test_inactive_user_cannot_sign_in(client: TestClient, world: World, db: Session) -> None:
    world.teacher_a.is_active = False
    db.commit()

    assert _login(client, "alice").json()["code"] == "auth.invalid_credentials"


def test_logout_revokes_the_session(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    assert user.post("/api/auth/logout").status_code == 204
    assert user.get("/api/auth/me").status_code == 401


def test_stolen_cookie_is_useless_after_logout(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")
    token = user.client.cookies[SESSION_COOKIE_NAME]
    user.post("/api/auth/logout")

    other = TestClient(app, cookies={SESSION_COOKIE_NAME: token})
    assert other.get("/api/auth/me").status_code == 401


def test_session_expires_after_idle_timeout(
    app: FastAPI, world: World, db: Session, settings: Settings
) -> None:
    user = ApiUser(app, "alice")
    session = db.scalars(select(UserSession)).one()
    db.execute(
        update(UserSession).values(
            last_seen_at=session.last_seen_at - timedelta(minutes=settings.session_idle_minutes + 1)
        )
    )
    db.commit()

    assert user.get("/api/auth/me").status_code == 401


def test_session_expires_after_absolute_lifetime(app: FastAPI, world: World, db: Session) -> None:
    user = ApiUser(app, "alice")
    session = db.scalars(select(UserSession)).one()
    db.execute(update(UserSession).values(expires_at=session.created_at))
    db.commit()

    assert user.get("/api/auth/me").status_code == 401


def test_only_token_hash_is_stored(app: FastAPI, world: World, db: Session) -> None:
    user = ApiUser(app, "alice")
    token = user.client.cookies[SESSION_COOKIE_NAME]

    stored = db.scalars(select(UserSession)).one()
    assert stored.token_hash != token
    assert token not in stored.token_hash


def test_throttle_blocks_after_repeated_failures(
    client: TestClient, world: World, settings: Settings
) -> None:
    for _ in range(settings.login_max_failures):
        assert _login(client, "alice", "wrong-password").status_code == 401

    blocked = _login(client, "alice")  # even the right password

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "auth.too_many_attempts"
    assert _login(client, "bruno").status_code == 200  # other users unaffected


def test_throttle_releases_after_window(
    client: TestClient, world: World, settings: Settings, db: Session
) -> None:
    for _ in range(settings.login_max_failures):
        _login(client, "alice", "wrong-password")
    for attempt in db.scalars(select(LoginAttempt)):
        attempt.attempted_at -= timedelta(minutes=settings.login_failure_window_minutes + 1)
    db.commit()

    assert _login(client, "alice").status_code == 200


def test_successful_login_resets_failure_count(
    client: TestClient, world: World, settings: Settings
) -> None:
    for _ in range(settings.login_max_failures - 1):
        _login(client, "alice", "wrong-password")
    assert _login(client, "alice").status_code == 200
    for _ in range(settings.login_max_failures - 1):
        _login(client, "alice", "wrong-password")

    assert _login(client, "alice").status_code == 200


def test_failed_attempts_are_recorded(client: TestClient, world: World, db: Session) -> None:
    _login(client, "alice", "wrong-password")

    attempt = db.scalars(select(LoginAttempt)).one()
    assert attempt.username == "alice"
    assert attempt.succeeded is False


def test_cross_origin_login_is_refused(client: TestClient, world: World) -> None:
    response = _login(client, "alice", origin="http://evil.example.com")

    assert response.status_code == 403
    assert response.json()["code"] == "auth.csrf_failed"


def test_same_origin_login_is_accepted(client: TestClient, world: World) -> None:
    assert _login(client, "alice", origin="http://testserver").status_code == 200


def test_language_preference_is_saved(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    response = user.put("/api/auth/me/language", json={"preferred_language": "fr"})

    assert response.status_code == 200
    assert user.get("/api/auth/me").json()["user"]["preferred_language"] == "fr"


def test_unsupported_language_is_rejected(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    assert user.put("/api/auth/me/language", json={"preferred_language": "de"}).status_code == 422


def test_password_never_echoed_in_validation_errors(client: TestClient, world: World) -> None:
    secret = "x" * 500  # too long: fails validation
    response = _login(client, "alice", secret)

    assert response.status_code == 422
    assert secret not in response.text


def test_production_cookie_is_secure(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"env": "production"}))
    Base.metadata.create_all(app.state.engine)
    with app.state.sessionmaker() as db:
        factory = Factory(db)
        factory.user(factory.school(), "alice")

    with TestClient(app) as client:
        response = _login(client, "alice")

    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    app.state.engine.dispose()


def test_sign_in_outcomes_are_logged_without_passwords(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.services.auth"):
        _login(client, "alice", "wrong-password")
        _login(client, "alice")

    assert "Sign-in failed username='alice'" in caplog.text
    assert "Sign-in succeeded username='alice'" in caplog.text
    assert "wrong-password" not in caplog.text
    assert PASSWORD not in caplog.text
