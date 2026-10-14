"""Sign-in throttling per username, based on recorded attempts."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import LoginAttempt


def is_locked_out(db: Session, username: str, *, settings: Settings, now: datetime) -> bool:
    """True if the username has too many failures in the window since its last success."""
    window_start = now - timedelta(minutes=settings.login_failure_window_minutes)
    last_success = db.scalar(
        select(func.max(LoginAttempt.attempted_at)).where(
            LoginAttempt.username == username, LoginAttempt.succeeded.is_(True)
        )
    )
    since = max(window_start, last_success) if last_success else window_start
    failures = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.username == username,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.attempted_at > since,
        )
    )
    return (failures or 0) >= settings.login_max_failures


def record_attempt(
    db: Session, username: str, *, succeeded: bool, now: datetime, client_ip: str | None
) -> None:
    db.add(
        LoginAttempt(username=username, succeeded=succeeded, attempted_at=now, client_ip=client_ip)
    )
