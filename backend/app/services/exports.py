"""Export guard (Phase 4). Phase 5's CSV and marked-PDF exports must take their scripts from
here: nothing a teacher has not confirmed can ever be exported (brief, non-negotiable)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Exam, Script, ScriptStatus
from app.errors import ConflictError


def exportable_scripts(db: Session, exam: Exam) -> list[Script]:
    """The exam's confirmed scripts only."""
    return list(
        db.scalars(
            select(Script)
            .where(Script.exam_id == exam.id, Script.status == ScriptStatus.CONFIRMED)
            .order_by(Script.id)
        )
    )


def require_confirmed(script: Script) -> None:
    if script.status != ScriptStatus.CONFIRMED or script.confirmed_at is None:
        raise ConflictError("Only confirmed scripts can be exported", code="export.not_confirmed")
