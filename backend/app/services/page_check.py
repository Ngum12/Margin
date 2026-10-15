"""Checking page orientation before AI marking (owner, 2026-10-15).

The reading model cannot tell which way up a page is (D-049), and one upside-down page cost a
student 3 marks in the owner's review. So a teacher looks at every page and turns any that are
wrong before AI marking may start. Adding pages (a new upload, or pages assigned from the tray)
clears the check so the new pages are looked at too.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db.models import Exam, Page, PageState, Script, User
from app.errors import ConflictError
from app.services import audit
from app.services.access import get_visible_exam


@dataclass(frozen=True)
class ScriptPages:
    script: Script
    pages: list[Page]


@dataclass(frozen=True)
class PageCheck:
    exam: Exam
    scripts: list[ScriptPages]


def page_check(db: Session, actor: User, exam_id: int) -> PageCheck:
    exam = get_visible_exam(db, actor, exam_id)
    scripts = list(db.scalars(select(Script).where(Script.exam_id == exam.id)))
    scripts.sort(key=lambda s: s.student.code)
    return PageCheck(
        exam,
        [ScriptPages(s, [p for p in s.pages if p.state == PageState.ASSIGNED]) for s in scripts],
    )


def mark_checked(db: Session, actor: User, exam_id: int) -> Exam:
    exam = get_visible_exam(db, actor, exam_id)
    if not db.scalar(select(Script.id).where(Script.exam_id == exam.id).limit(1)):
        raise ConflictError("No scripts have been uploaded yet", code="ai.no_scripts")
    exam.pages_checked_at = utcnow()
    exam.pages_checked_by_id = actor.id
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="pages_checked",
        new_value={"checked_at": exam.pages_checked_at.isoformat()},
    )
    return exam


def clear_check(exam: Exam) -> None:
    """New pages arrived: they have not been looked at yet."""
    exam.pages_checked_at = None
    exam.pages_checked_by_id = None


def require_checked(exam: Exam) -> None:
    if exam.pages_checked_at is None:
        raise ConflictError(
            "Check page orientation before AI marking", code="exam.pages_not_checked"
        )
