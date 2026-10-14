"""Is the background worker running, and can the model server be reached? Shown to teachers so
the app says what is wrong instead of waiting silently."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.ollama_client import OllamaClient
from app.ai.types import ModelUnavailableError
from app.clock import utcnow
from app.config import Settings
from app.db.models import WorkerHeartbeat

WORKER_ONLINE_WITHIN = timedelta(seconds=60)
MODEL_CHECK_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class ModelServerStatus:
    backend: str
    reachable: bool
    reader_model_installed: bool
    marker_model_installed: bool


def worker_online(db: Session) -> bool:
    last = db.scalar(select(func.max(WorkerHeartbeat.seen_at)))
    return last is not None and utcnow() - last < WORKER_ONLINE_WITHIN


def model_server_status(settings: Settings) -> ModelServerStatus:
    if settings.ai_backend == "mock":
        return ModelServerStatus("mock", True, True, True)
    client = OllamaClient(settings.model_base_url, MODEL_CHECK_TIMEOUT_SECONDS)
    try:
        models = client.list_models()
    except ModelUnavailableError:
        return ModelServerStatus("ollama", False, False, False)

    def installed(name: str) -> bool:
        return name in models or f"{name}:latest" in models

    return ModelServerStatus(
        "ollama", True, installed(settings.reader_model), installed(settings.marker_model)
    )
