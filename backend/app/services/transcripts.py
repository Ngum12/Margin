"""Which transcription of a page is the current one. Shared by marking and review."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Transcription


def page_versions(db: Session, page_id: int) -> list[Transcription]:
    """Every transcription of a page, oldest first. Rows are never changed or deleted."""
    return list(
        db.scalars(
            select(Transcription)
            .where(Transcription.page_id == page_id)
            .order_by(Transcription.created_at, Transcription.id)
        )
    )


def current(versions: Sequence[Transcription]) -> Transcription | None:
    """The newest version wins, whoever made it: a teacher edit supersedes the model's read, and
    a fresh read the teacher asked for (after correcting the orientation) supersedes both."""
    return max(versions, key=lambda t: (t.created_at, t.id), default=None)
