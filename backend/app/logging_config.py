"""Structured logging to local rotating files.

Never log student transcriptions, names or images. Log identifiers (codes, ids) only.
"""

import json
import logging
import logging.handlers
from datetime import UTC, datetime

from app.config import Settings

_HANDLER_NAME = "margin-file"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    """Attach a rotating JSON file handler to the root logger. Safe to call more than once."""
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    if any(h.get_name() == _HANDLER_NAME for h in root.handlers):
        return

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        settings.log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
