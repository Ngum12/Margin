"""Database-backed sessions (D-015). The cookie holds a random token; only its hash is stored."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.config import Settings
from app.db.models import User, UserSession

SESSION_COOKIE_NAME = "margin_session"
CSRF_HEADER_NAME = "X-CSRF-Token"

# Avoid a database write on every request: refresh last_seen_at at most this often.
_TOUCH_INTERVAL = timedelta(minutes=1)


@dataclass(frozen=True)
class NewSession:
    token: str
    session: UserSession


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    db: Session, user: User, *, settings: Settings, now: datetime, user_agent: str | None
) -> NewSession:
    token = secrets.token_urlsafe(32)
    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_hours),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(user_session)
    db.flush()
    return NewSession(token=token, session=user_session)


def find_active_session(
    db: Session, token: str, *, settings: Settings, now: datetime
) -> UserSession | None:
    """Return the session for ``token`` if it is valid now, refreshing its idle timer."""
    user_session = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.token_hash == hash_token(token))
    )
    if user_session is None or user_session.revoked_at is not None:
        return None
    idle_limit = user_session.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if now >= user_session.expires_at or now >= idle_limit or not user_session.user.is_active:
        return None
    if now - user_session.last_seen_at >= _TOUCH_INTERVAL:
        user_session.last_seen_at = now
    return user_session


def revoke_session(user_session: UserSession, *, now: datetime) -> None:
    user_session.revoked_at = now


def revoke_all_for_user(db: Session, user_id: int, *, now: datetime) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def csrf_token_matches(user_session: UserSession, supplied: str | None) -> bool:
    return supplied is not None and hmac.compare_digest(user_session.csrf_token, supplied)
