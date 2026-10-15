"""The mark decisions a teacher works on, shared by review, results, exports and provenance."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MarkDecision, Question, Script


def exam_questions(db: Session, exam_id: int) -> list[Question]:
    return list(
        db.scalars(select(Question).where(Question.exam_id == exam_id).order_by(Question.position))
    )


def current_decisions(
    db: Session, script_ids: Iterable[int]
) -> dict[tuple[int, int], MarkDecision]:
    """(script id, point id) -> the decision row the teacher works on: the newest row per point
    of the script's current AI run (earlier runs are history). A teacher-only row is created
    only when no row exists, so the newest row is always the latest AI proposal when there is
    one."""
    ids = list(script_ids)
    if not ids:
        return {}
    rows = db.scalars(
        select(MarkDecision)
        .join(Script, MarkDecision.script_id == Script.id)
        .where(MarkDecision.script_id.in_(ids), MarkDecision.ai_run == Script.ai_run)
        .order_by(MarkDecision.id)
    )
    return {(d.script_id, d.mark_scheme_point_id): d for d in rows}
