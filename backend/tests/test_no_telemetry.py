"""FastAPI's native OpenTelemetry support must stay off, whatever the environment says."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_telemetry_env_vars_cannot_enable_export(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    # With auto-configuration honoured, these would make FastAPI try to set up an OTLP
    # exporter (and fail at startup because the OpenTelemetry SDK is not installed).
    monkeypatch.setenv("FASTAPI_OTEL_AUTO_CONFIGURE", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example.com:4318")

    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    assert app._telemetry["auto_configure"] is False
    assert app._native_telemetry.enabled() is False


def test_opentelemetry_sdk_and_exporters_are_not_installed() -> None:
    with pytest.raises(ImportError):
        __import__("opentelemetry.sdk")
    with pytest.raises(ImportError):
        __import__("opentelemetry.exporter.otlp")
