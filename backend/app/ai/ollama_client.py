"""Minimal client for the local Ollama HTTP API, standard library only (D-038).

This is the only module in the application that opens network connections (a test enforces
it), and it only talks to the configured model host.
"""

import base64
import http.client
import json
from typing import Any
from urllib.parse import urlsplit

from app.ai.types import ModelOutputInvalidError, ModelUnavailableError


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        think: bool | None = None,
        max_output_tokens: int | None = None,
        context_tokens: int | None = None,
    ) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("model_base_url must be an http(s) URL")
        self._https = parts.scheme == "https"
        self._host = parts.hostname
        self._port = parts.port or (443 if self._https else 80)
        self._prefix = parts.path.rstrip("/")
        self._timeout = timeout_seconds
        # None: leave it to the model's default; True/False: Ollama's "think" switch.
        self._think = think
        self._options: dict[str, Any] = {"temperature": 0}
        if max_output_tokens is not None:
            self._options["num_predict"] = max_output_tokens
        if context_tokens is not None:
            self._options["num_ctx"] = context_tokens

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
        body: dict[str, Any] = {
            "model": model,
            "messages": [message],
            "stream": False,
            "format": schema,
            "options": self._options,
            "keep_alive": "30m",
        }
        if self._think is not None:
            body["think"] = self._think
        data = self._request("POST", "/api/chat", body)
        content = data.get("message", {}).get("content")
        if not isinstance(content, str):
            raise ModelUnavailableError("bad_response")
        if data.get("done_reason") == "length":
            # Cut off at the output cap (or the context filled up, e.g. by long "thinking"):
            # whatever came back is incomplete and must not be used.
            raise ModelOutputInvalidError("output_cut_off")
        return content
