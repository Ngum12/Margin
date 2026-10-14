import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.startup_checks import UnsafeConfigurationError, check_startup_safety


def _production(settings: Settings, **overrides: object) -> Settings:
    return settings.model_copy(update={"env": "production", **overrides})


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
    monkeypatch.setenv("MARGIN_COOKIE_SECURE", "false")

    with pytest.raises(UnsafeConfigurationError):
        check_startup_safety(Settings(_env_file=None))

    monkeypatch.setenv("MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION", "true")
    check_startup_safety(Settings(_env_file=None))
