from fastapi import FastAPI
from fastapi.telemetry import TelemetryConfig

from app import __version__
from app.api import api_router
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.security_headers import SecurityHeadersMiddleware
from app.spa import mount_spa
from app.startup_checks import check_startup_safety

TELEMETRY_DISABLED: TelemetryConfig = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
    "auto_configure": False,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    check_startup_safety(settings)

    is_dev = settings.env == "development"
    app = FastAPI(
        title="Marking Assistant",
        version=__version__,
        # FastAPI ships native OpenTelemetry hooks that environment variables can switch on.
        # No telemetry is a non-negotiable, so disable all of it explicitly (D-013).
        telemetry=TELEMETRY_DISABLED,
        # Interactive API docs load assets from a CDN, so they are only enabled in development.
        docs_url="/api/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if is_dev else None,
    )
    app.state.settings = settings
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(api_router, prefix="/api")
    mount_spa(app, settings.frontend_dist)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory app.main:app_factory``."""
    return create_app()
