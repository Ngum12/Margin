"""Sign-in. One generic error for unknown users, wrong passwords and inactive accounts."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import passwords, throttle
from app.config import Settings
from app.db.models import User
from app.errors import AuthenticationError, TooManyAttemptsError

# Staff usernames and outcomes only. Never log passwords.
logger = logging.getLogger(__name__)


def authenticate(
    db: Session,
    username: str,
    password: str,
    *,
    settings: Settings,
    now: datetime,
    client_ip: str | None,
) -> User:
    username = username.strip().lower()
    if throttle.is_locked_out(db, username, settings=settings, now=now):
        logger.warning("Sign-in refused (throttled) username=%r ip=%s", username, client_ip)
        raise TooManyAttemptsError("Too many failed sign-in attempts; try again later")

    user = db.scalar(select(User).where(User.username == username)) if username else None
    if user is None:
        passwords.burn_verification_time(password)
        ok = False
    else:
        ok = passwords.verify_password(user.password_hash, password) and user.is_active

    throttle.record_attempt(db, username, succeeded=ok, now=now, client_ip=client_ip)
    if not ok or user is None:
        logger.info("Sign-in failed username=%r ip=%s", username, client_ip)
        # Commit here so the failed attempt is kept although the request ends in an error.
        db.commit()
        raise AuthenticationError(
            "Username or password is incorrect", code="auth.invalid_credentials"
        )

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    user.last_login_at = now
    logger.info("Sign-in succeeded username=%r ip=%s", username, client_ip)
    return user
