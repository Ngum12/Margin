"""Application settings, loaded from environment variables (prefix ``MARGIN_``) or a local ``.env``.

Every setting here must also be documented in ``.env.example`` at the repository root.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARGIN_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "production", "test"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Uploaded scans, page images, logs and the database live here. Never publicly served.
    data_dir: Path = REPO_ROOT / "data"

    # Built frontend (``npm run build`` output). Served by the backend when it exists.
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    # The only host the application may contact over the network (local model server).
    model_base_url: str = "http://127.0.0.1:11434"
    # Refuse to start with a public model host unless explicitly allowed (D-040).
    allow_public_model_host: bool = False

    # AI backend: "mock" (deterministic, no model server) or "ollama".
    ai_backend: Literal["mock", "ollama"] = "mock"
    # Instruct variants: the plain qwen3-vl tags are "thinking" models (D-046).
    reader_model: str = "qwen3-vl:8b-instruct"
    marker_model: str = "qwen3-vl:8b-instruct"
    # Seconds to wait for one model reply; slow machines may need a lot (see the Phase 3 report).
    model_timeout_seconds: int = Field(default=900, ge=5)
    # Extra attempts when the model replies with output that fails validation.
    model_output_retries: int = Field(default=2, ge=0, le=5)
    # Models with a "thinking" mode (e.g. Qwen3-VL) reason before replying when this is true.
    # Off by default: much faster on modest hardware; see docs/DECISIONS.md D-046.
    model_think: bool = False
    # Hard cap on tokens per model reply: a model that rambles (or reasons at length) is cut off
    # and its reply treated as invalid, instead of occupying the machine for many minutes.
    model_max_output_tokens: int = Field(default=2048, ge=64)
    # Model context window (prompt + image + reply). Ollama's default of 4096 is too small for a
    # page image plus prompt plus reply.
    model_context_tokens: int = Field(default=8192, ge=2048)
    # Page images are shrunk to at most this many pixels on the long side before sending.
    reader_max_image_px: int = Field(default=1600, ge=512, le=4000)
    # Mock models only: artificial delay per call in seconds (demos and tests).
    mock_delay_seconds: float = Field(default=0.0, ge=0)

    # Background jobs.
    job_max_attempts: int = Field(default=6, ge=1)
    worker_poll_seconds: float = Field(default=2.0, gt=0)
    # A running job whose worker has not sent a heartbeat for this long is treated as abandoned
    # (crash, power cut) and run again. The worker heartbeats at a third of this interval.
    job_stale_seconds: float = Field(default=120.0, ge=1)

    # Session cookies carry the `Secure` flag (sent over HTTPS only). Unset means: on in
    # production, off in development and test. See docs/DECISIONS.md D-016.
    cookie_secure: bool | None = None

    # Production refuses to start with insecure cookies unless this is explicitly true.
    # Only for a deliberate, temporary plain-HTTP deployment on a trusted network.
    allow_insecure_cookies_in_production: bool = False

    # SQLAlchemy URL. Unset: SQLite file at <data_dir>/margin.db.
    database_url: str | None = None

    # Sessions end after this much inactivity, and in any case after the absolute lifetime.
    session_idle_minutes: int = Field(default=120, ge=5)
    session_absolute_hours: int = Field(default=12, ge=1)

    # Sign-in throttling: this many failures for a username within the window blocks
    # further attempts until the window has passed.
    login_max_failures: int = Field(default=5, ge=1)
    login_failure_window_minutes: int = Field(default=15, ge=1)

    # Scanned PDF uploads. Rendering runs in a child process that is killed after the timeout.
    max_upload_mb: int = Field(default=500, ge=1)
    max_pdf_pages: int = Field(default=1000, ge=1)
    render_timeout_seconds: int = Field(default=900, ge=1)
    # Page images: resolution and JPEG quality (D-031).
    page_dpi: int = Field(default=200, ge=100, le=400)
    page_jpeg_quality: int = Field(default=90, ge=50, le=100)

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'margin.db').as_posix()}"

    @property
    def session_cookie_secure(self) -> bool:
        if self.cookie_secure is None:
            return self.env == "production"
        return self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
