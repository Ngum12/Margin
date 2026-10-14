"""Append-only cache that makes long evaluation runs resumable.

Each finished model call (one page read, one script marked) is written as one JSON line and
flushed to disk immediately. Re-running the same evaluation skips calls already in the cache.
Keys include the model, its version, the prompt versions, the image size setting and a hash of
the input, so a result is never reused for a different configuration.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class EvalCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, Any] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a line cut short by an interruption: ignore it, the call reruns
                self._entries[entry["key"]] = entry["value"]

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> Any | None:
        return self._entries.get(key)

    def put(self, key: str, value: Any) -> None:
        self._entries[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "value": value}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
