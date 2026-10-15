"""Configuration safety checks run before the app (and later the worker) starts.

A failed check stops startup with a plain-language message instead of running unsafely.
"""

import ipaddress
import logging
from urllib.parse import urlsplit

from app.config import Settings

logger = logging.getLogger(__name__)


class UnsafeConfigurationError(RuntimeError):
    """Raised when settings would run the application in an unsafe way."""


INSECURE_COOKIES_MESSAGE = (
    "Refusing to start: production mode with secure cookies switched off "
    "(MARGIN_COOKIE_SECURE=false). Serve the app over HTTPS and enable secure cookies. "
    "If you must run over plain HTTP temporarily on a trusted network, set "
    "MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION=true."
)


MOCK_IN_PRODUCTION_MESSAGE = (
    "Refusing to start: production mode with the test AI backend (MARGIN_AI_BACKEND=mock). "
    "The test models do not read or mark scripts; their output is not real AI marking. "
    "Set MARGIN_AI_BACKEND=ollama in the .env file and start again."
)


PUBLIC_MODEL_HOST_MESSAGE = (
    "Refusing to start: the model server ({host}) is not on this computer or the school's "
    "private network, so student work would leave the school. Use a local Ollama address "
    "(e.g. http://127.0.0.1:11434 or a private network address). To allow it deliberately, set "
    "MARGIN_ALLOW_PUBLIC_MODEL_HOST=true."
)


def model_host_is_local(base_url: str) -> bool:
    """Loopback, private or link-local addresses, ``localhost``, single-label names (e.g. the
    Docker service ``ollama``) and ``.local``/``.lan`` names count as on the school network."""
    host = (urlsplit(base_url).hostname or "").lower()
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith((".local", ".lan"))
    return address.is_loopback or address.is_private or address.is_link_local


def check_startup_safety(settings: Settings) -> None:
    if settings.env == "production" and settings.ai_backend == "mock":
        raise UnsafeConfigurationError(MOCK_IN_PRODUCTION_MESSAGE)
    if not settings.allow_public_model_host and not model_host_is_local(settings.model_base_url):
        host = urlsplit(settings.model_base_url).hostname or settings.model_base_url
        raise UnsafeConfigurationError(PUBLIC_MODEL_HOST_MESSAGE.format(host=host))
    _check_cookies(settings)


def _check_cookies(settings: Settings) -> None:
    if settings.env != "production" or settings.session_cookie_secure:
        return
    if not settings.allow_insecure_cookies_in_production:
        raise UnsafeConfigurationError(INSECURE_COOKIES_MESSAGE)
    logger.warning(
        "Running in production with insecure cookies because "
        "MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION=true. Session cookies can be read on the "
        "network. Enable HTTPS as soon as possible."
    )
