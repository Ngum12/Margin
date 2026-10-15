import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.startup_checks import UnsafeConfigurationError, check_startup_safety


def _production(settings: Settings, **overrides: object) -> Settings:
    """Production with a real AI backend (the test backend is refused in production)."""
    return settings.model_copy(update={"env": "production", "ai_backend": "ollama", **overrides})


def test_production_defaults_to_secure_cookies(settings: Settings) -> None:
    production = _production(settings)

    assert production.session_cookie_secure is True
    check_startup_safety(production)


@pytest.mark.parametrize("env", ["development", "test"])
def test_non_production_defaults_to_insecure_cookies(settings: Settings, env: str) -> None:
    assert settings.model_copy(update={"env": env}).session_cookie_secure is False


def test_production_refuses_to_start_with_insecure_cookies(settings: Settings) -> None:
    production = _production(settings, cookie_secure=False)

    with pytest.raises(UnsafeConfigurationError, match="MARGIN_COOKIE_SECURE"):
        create_app(production)


def test_explicit_override_allows_start_and_warns(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    production = _production(
        settings, cookie_secure=False, allow_insecure_cookies_in_production=True
    )

    with caplog.at_level(logging.WARNING, logger="app.startup_checks"):
        app = create_app(production)

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
    assert "insecure cookies" in caplog.text


def test_settings_from_environment_are_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARGIN_ENV", "production")
    monkeypatch.setenv("MARGIN_AI_BACKEND", "ollama")
    monkeypatch.setenv("MARGIN_COOKIE_SECURE", "false")

    with pytest.raises(UnsafeConfigurationError):
        check_startup_safety(Settings(_env_file=None))

    monkeypatch.setenv("MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION", "true")
    check_startup_safety(Settings(_env_file=None))


# --- the test AI backend (owner, 2026-10-15) --------------------------------------------------


def test_production_refuses_to_start_with_the_test_ai_backend(settings: Settings) -> None:
    production = _production(settings, ai_backend="mock")

    with pytest.raises(UnsafeConfigurationError, match="MARGIN_AI_BACKEND=mock") as raised:
        create_app(production)
    assert "not real AI marking" in str(raised.value)


def test_production_backend_from_the_environment_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARGIN_ENV", "production")
    monkeypatch.delenv("MARGIN_AI_BACKEND", raising=False)
    with pytest.raises(UnsafeConfigurationError, match="test AI backend"):
        check_startup_safety(Settings(_env_file=None))  # the default backend is mock
    monkeypatch.setenv("MARGIN_AI_BACKEND", "ollama")
    check_startup_safety(Settings(_env_file=None))


@pytest.mark.parametrize("env", ["development", "test"])
def test_the_test_backend_is_allowed_outside_production(settings: Settings, env: str) -> None:
    check_startup_safety(settings.model_copy(update={"env": env, "ai_backend": "mock"}))


def test_the_worker_refuses_the_test_backend_in_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker.__main__ import main as worker_main

    monkeypatch.setenv("MARGIN_ENV", "production")
    monkeypatch.setenv("MARGIN_AI_BACKEND", "mock")
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert worker_main() == 2
    finally:
        get_settings.cache_clear()
