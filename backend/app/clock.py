from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime. The only clock the app uses."""
    return datetime.now(UTC)
