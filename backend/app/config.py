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

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
