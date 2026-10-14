"""Minimal client for the local Ollama HTTP API, standard library only (D-038).

This is the only module in the application that opens network connections (a test enforces
it), and it only talks to the configured model host.
"""

import base64
import http.client
import json
from typing import Any
from urllib.parse import urlsplit

from app.ai.types import ModelUnavailableError


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("model_base_url must be an http(s) URL")
        self._https = parts.scheme == "https"
        self._host = parts.hostname
        self._port = parts.port or (443 if self._https else 80)
        self._prefix = parts.path.rstrip("/")
        self._timeout = timeout_seconds

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        connection_class = (
            http.client.HTTPSConnection if self._https else http.client.HTTPConnection
        )
        connection = connection_class(self._host, self._port, timeout=self._timeout)
        try:
            payload = json.dumps(body).encode("utf-8") if body is not None else None
            headers = {"Content-Type": "application/json"} if payload else {}
            connection.request(method, self._prefix + path, body=payload, headers=headers)
            response = connection.getresponse()
            data = response.read()
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            raise ModelUnavailableError(type(exc).__name__) from exc
        finally:
            connection.close()
        if response.status >= 500:
            raise ModelUnavailableError(f"http_{response.status}")
        if response.status >= 400:
            # e.g. 404 model not found: a configuration problem, not worth hammering.
            raise ModelUnavailableError(f"http_{response.status}")
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            raise ModelUnavailableError("bad_response") from exc

    def list_models(self) -> dict[str, str]:
        """Installed models: name -> digest."""
        data = self._request("GET", "/api/tags")
        return {m["name"]: m.get("digest", "") for m in data.get("models", [])}

    def models_with_capability(self, capability: str) -> list[str]:
        """Installed models that report a capability, e.g. "vision"."""
        data = self._request("GET", "/api/tags")
        return sorted(
            m["name"] for m in data.get("models", []) if capability in (m.get("capabilities") or [])
        )

    def chat_json(
        self,
        model: str,
        prompt: str,
        schema: dict[str, Any],
        images: list[bytes] | None = None,
    ) -> str:
        """One deterministic chat turn with JSON output constrained by ``schema``.
        Returns the raw content string; the caller validates it."""
        message: dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            message["images"] = [base64.b64encode(image).decode("ascii") for image in images]
        data = self._request(
            "POST",
            "/api/chat",
            {
                "model": model,
                "messages": [message],
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
                "keep_alive": "30m",
            },
        )
        content = data.get("message", {}).get("content")
        if not isinstance(content, str):
            raise ModelUnavailableError("bad_response")
        return content
