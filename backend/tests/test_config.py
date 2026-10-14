from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.logging_config import configure_logging


def test_settings_read_margin_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MARGIN_ENV", "production")
    monkeypatch.setenv("MARGIN_PORT", "9123")
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MARGIN_MODEL_BASE_URL", "http://192.168.1.20:11434")

    settings = Settings(_env_file=None)

    assert settings.env == "production"
    assert settings.port == 9123
    assert settings.data_dir == tmp_path
    assert settings.log_dir == tmp_path / "logs"
    assert settings.model_base_url == "http://192.168.1.20:11434"


def test_settings_reject_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARGIN_ENV", "staging")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_default_model_host_is_local() -> None:
    assert Settings(_env_file=None).model_base_url == "http://127.0.0.1:11434"


def test_logging_writes_json_to_data_dir(settings: Settings) -> None:
    import json
    import logging

    configure_logging(settings)
    configure_logging(settings)  # idempotent: no duplicate handlers
    logging.getLogger("test").warning("hello")
    for handler in logging.getLogger().handlers:
        handler.flush()

    lines = (settings.log_dir / "app.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["message"] == "hello"
    assert record["level"] == "WARNING"
