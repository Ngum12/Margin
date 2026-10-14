"""Configuration safety checks run before the app (and later the worker) starts.

A failed check stops startup with a plain-language message instead of running unsafely.
"""

import logging

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


def check_startup_safety(settings: Settings) -> None:
    if settings.env != "production" or settings.session_cookie_secure:
        return
    if not settings.allow_insecure_cookies_in_production:
        raise UnsafeConfigurationError(INSECURE_COOKIES_MESSAGE)
    logger.warning(
        "Running in production with insecure cookies because "
        "MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION=true. Session cookies can be read on the "
        "network. Enable HTTPS as soon as possible."
    )
