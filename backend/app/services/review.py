"""Teacher review (Phase 4): the marking queue, the script review screen, every teacher edit,
confirm and reopen, and review time.

Rules:
- Every change writes exactly one audit event per changed item, with old and new values.
- Nothing the AI proposed is final until a teacher decides it; a script is final only when a
  teacher confirms it, and a confirmed script is locked until reopened.
- Review time is stored in the school database only and is never sent anywhere.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import Settings
from app.db.models import (
    ErrorCategory,
    Exam,
    ExamStatus,
    Job,
    JobStatus,
    JobType,
    MarkDecision,
    MarkSchemePoint,
    Page,
    PageState,
    PrintJob,
    Question,
    QuestionComment,
    ReviewSession,
    Script,
    ScriptStatus,
    Transcription,
    TranscriptionSource,
    User,
)
from app.errors import ConflictError, Issue, NotFoundError, ValidationFailedError
from app.marks import HALF_MARKS_ALLOWED, HALF_MARKS_PER_MARK, from_half_marks
from app.schemas.review import (
    COMMENT_MAX_LENGTH,
    Marks,
    QueueItemOut,
    QueueOut,
    ReviewExamOut,
    ReviewNavigationOut,
    ReviewPageOut,
    ReviewPointOut,
    ReviewQuestionOut,
    ReviewScriptOut,
    ReviewTotalsOut,
    ScriptReviewOut,
    TranscriptionVersionOut,
)
from app.services import audit, jobs, transcripts
from app.services.access import get_visible_exam, get_visible_script
from app.services.ai_marking import script_is_done
from app.services.decisions import current_decisions, exam_questions
from app.services.page_counts import page_count_flag, typical_page_count
from app.services.provenance import test_model_scripts
from app.services.scoring import score_question
from app.services.uploads import get_visible_page

# Review time (owner change 2): a heartbeat arrives every 30 s while the screen is in use.
IDLE_GAP = timedelta(minutes=5)  # longer gaps are not counted as review time
HEARTBEAT_MAX_SECONDS = 60.0  # at most this much is added per heartbeat

# The order the "c" key cycles through, and the default for a fresh teacher decision.
CATEGORY_ORDER = (
    ErrorCategory.CORRECT,
    ErrorCategory.CONCEPTUAL_ERROR,
    ErrorCategory.LANGUAGE_EXPRESSION,
    ErrorCategory.TRANSCRIPTION_UNCERTAIN,
    ErrorCategory.OMITTED,
)


# --- shared helpers ---------------------------------------------------------------------------


def is_reviewable(script: Script) -> bool:
    """The AI has finished with the script (or flagged it for manual marking)."""
    return script.status == ScriptStatus.CONFIRMED or script_is_done(script)


def _editable_script(db: Session, actor: User, script_id: int) -> Script:
    script = get_visible_script(db, actor, script_id)
    _require_editable(script)
    return script


def _require_editable(script: Script) -> None:
    if script.status == ScriptStatus.CONFIRMED:
        raise ConflictError("Script is confirmed; reopen it first", code="script.confirmed")
    if not is_reviewable(script):
        raise ConflictError("AI marking has not finished for this script", code="script.not_ready")


def _touch(script: Script) -> None:
    """First teacher edit: record it, and move an AI-marked script into review."""
    if script.reviewed_at is None:
        script.reviewed_at = utcnow()
    if script.status != ScriptStatus.CONFIRMED:
        script.status = ScriptStatus.IN_REVIEW


def _point_of_exam(db: Session, exam_id: int, point_id: int) -> MarkSchemePoint:
    point = db.scalar(
        select(MarkSchemePoint)
        .join(Question, MarkSchemePoint.question_id == Question.id)
        .where(MarkSchemePoint.id == point_id, Question.exam_id == exam_id)
    )
    if point is None:
        raise NotFoundError("Point")
    return point


def _decision_for(db: Session, script: Script, point: MarkSchemePoint) -> MarkDecision:
    decision = current_decisions(db, [script.id]).get((script.id, point.id))
    if decision is None:
        # Manual marking (or a question the AI failed): a row with no AI proposal.
        decision = MarkDecision(
            script_id=script.id,
            mark_scheme_point_id=point.id,
            proposed_at=None,
            ai_run=script.ai_run,
        )
        db.add(decision)
        db.flush()
    return decision


def _decision_value(decision: MarkDecision) -> dict[str, object]:
    return {
        "marks": (
            None
            if decision.final_half_marks is None
            else from_half_marks(decision.final_half_marks)
        ),
        "category": decision.final_category.value if decision.final_category else None,
    }


def _half_marks(marks: Marks, point: MarkSchemePoint) -> int:
    half = marks * HALF_MARKS_PER_MARK
    whole_only = not HALF_MARKS_ALLOWED and float(marks) != int(marks)
    if whole_only or float(half) != int(half) or not 0 <= half <= point.half_marks:
        raise ValidationFailedError(
            "Marks must be a whole number from 0 to the point's maximum",
            code="decision.marks_out_of_range",
            issues=[
                Issue("decision.marks_out_of_range", ["marks"], {"max": point.half_marks // 2})
            ],
        )
    return int(half)


# --- decisions --------------------------------------------------------------------------------


def set_decision(
    db: Session,
    actor: User,
    script_id: int,
    point_id: int,
    marks: Marks | None,
    category: ErrorCategory | None,
) -> None:
    if marks is None and category is None:
        raise ValidationFailedError("Give marks or a category", code="decision.empty")
    script = _editable_script(db, actor, script_id)
    point = _point_of_exam(db, script.exam_id, point_id)
    half = None if marks is None else _half_marks(marks, point)
    decision = _decision_for(db, script, point)
    old = _decision_value(decision)

    if half is not None:
        decision.final_half_marks = half
    if category is not None:
        decision.final_category = category
    elif decision.final_category is None and decision.final_half_marks is not None:
        # A fresh decision needs a category too: take the AI's, or "correct" for full marks.
        if decision.error_category is not None:
            decision.final_category = decision.error_category
        elif decision.final_half_marks == point.half_marks:
            decision.final_category = ErrorCategory.CORRECT
    new = _decision_value(decision)
    if new == old:
        return
    decision.decided_by_id = actor.id
    decision.decided_at = utcnow()
    _touch(script)
    audit.record(
        db,
        actor=actor,
        entity_type="mark_decision",
        entity_id=decision.id,
        action="set_decision",
        old_value=old,
        new_value=new,
    )


def _accept(
    db: Session, actor: User, decision: MarkDecision, action: str, *, keep_category: bool = False
) -> bool:
    """Copy the AI's proposal into the final fields. With ``keep_category``, a category the
    teacher already chose is kept and only the missing mark is filled in."""
    if decision.proposed_half_marks is None or decision.error_category is None:
        return False
    old = _decision_value(decision)
    decision.final_half_marks = decision.proposed_half_marks
    if not (keep_category and decision.final_category is not None):
        decision.final_category = decision.error_category
    new = _decision_value(decision)
    if new == old:
        return False
    decision.decided_by_id = actor.id
    decision.decided_at = utcnow()
    audit.record(
        db,
        actor=actor,
        entity_type="mark_decision",
        entity_id=decision.id,
        action=action,
        old_value=old,
        new_value=new,
    )
    return True


def accept_point(db: Session, actor: User, script_id: int, point_id: int) -> None:
    script = _editable_script(db, actor, script_id)
    point = _point_of_exam(db, script.exam_id, point_id)
    decision = current_decisions(db, [script.id]).get((script.id, point.id))
    if decision is None or decision.proposed_half_marks is None:
        raise ConflictError("There is no AI proposal for this point", code="decision.no_proposal")
    if _accept(db, actor, decision, "accept"):
        _touch(script)


def accept_all(db: Session, actor: User, script_id: int) -> int:
    """Accept the AI's proposal for every point that has no final mark yet. Teacher decisions are
    kept: a point the teacher already marked is skipped, and a category the teacher chose before
    accepting stays (owner's review, 2026-10-15: changing categories first left marks empty)."""
    script = _editable_script(db, actor, script_id)
    accepted = 0
    for decision in current_decisions(db, [script.id]).values():
        if decision.final_half_marks is None:
            accepted += _accept(db, actor, decision, "accept_all", keep_category=True)
    if accepted:
        _touch(script)
    return accepted


# --- comments ---------------------------------------------------------------------------------


def set_comment(db: Session, actor: User, script_id: int, question_id: int, text: str) -> None:
    script = _editable_script(db, actor, script_id)
    question = db.get(Question, question_id)
    if question is None or question.exam_id != script.exam_id:
        raise NotFoundError("Question")
    text = text.strip()
    if len(text) > COMMENT_MAX_LENGTH:
        raise ValidationFailedError(
            "Comment too long",
            code="comment.too_long",
            issues=[Issue("comment.too_long", ["text"], {"max": COMMENT_MAX_LENGTH})],
        )
    row = db.scalar(
        select(QuestionComment).where(
            QuestionComment.script_id == script.id, QuestionComment.question_id == question.id
        )
    )
    old = row.text if row else ""
    if old == text:
        return
    if not text and row is not None:
        db.delete(row)
        entity_id = row.id
    elif row is None:
        row = QuestionComment(
            script_id=script.id, question_id=question.id, text=text, updated_by_id=actor.id
        )
        db.add(row)
        db.flush()
        entity_id = row.id
    else:
        row.text, row.updated_by_id, row.updated_at = text, actor.id, utcnow()
        entity_id = row.id
    _touch(script)
    audit.record(
        db,
        actor=actor,
        entity_type="question_comment",
        entity_id=entity_id,
        action="set_comment",
        old_value={"script_id": script.id, "question_id": question.id, "text": old},
        new_value={"script_id": script.id, "question_id": question.id, "text": text},
    )


# --- transcriptions ---------------------------------------------------------------------------


def _script_page(db: Session, actor: User, page_id: int) -> tuple[Page, Script]:
    page = get_visible_page(db, actor, page_id)
    if page.script_id is None or page.state != PageState.ASSIGNED:
        raise ConflictError("The page is not part of a script", code="page.not_in_script")
    script = db.get(Script, page.script_id)
    if script is None:  # pragma: no cover
        raise NotFoundError("Script")
    return page, script


def edit_transcription(db: Session, actor: User, page_id: int, text: str) -> None:
    """Save the teacher's text as a new version; earlier versions are kept unchanged."""
    page, script = _script_page(db, actor, page_id)
    _require_editable(script)
    if page.is_cover:
        raise ConflictError("Cover sheets are not transcribed", code="page.is_cover")
    found = transcripts.current(transcripts.page_versions(db, page.id))
    old = found.text if found else None
    if old == text:
        return
    row = Transcription(
        script_id=script.id,
        page_id=page.id,
        text=text,
        source=TranscriptionSource.TEACHER,
        created_by_id=actor.id,
        created_at=utcnow(),
        rotation=page.effective_rotation,
    )
    db.add(row)
    db.flush()
    _touch(script)
    # The audit log is in the database; transcription text never goes to log files.
    audit.record(
        db,
        actor=actor,
        entity_type="page",
        entity_id=page.id,
        action="edit_transcription",
        old_value={"text": old, "transcription_id": found.id if found else None},
        new_value={"text": text, "transcription_id": row.id},
    )


# --- orientation (layers a and c) -------------------------------------------------------------


def _has_model_read(db: Session, page_id: int) -> bool:
    found = db.scalar(
        select(Transcription.id)
        .where(Transcription.page_id == page_id, Transcription.source == TranscriptionSource.MODEL)
        .limit(1)
    )
    return found is not None


def _rotation_value(page: Page) -> dict[str, object]:
    return {
        "rotation": page.effective_rotation,
        "rotation_teacher": page.rotation_teacher,
        "rotation_auto": page.rotation_auto,
    }


def _page_for_orientation(db: Session, actor: User, page_id: int) -> Page:
    page = get_visible_page(db, actor, page_id)
    script = db.get(Script, page.script_id) if page.script_id else None
    if script is not None and script.status == ScriptStatus.CONFIRMED:
        raise ConflictError("Script is confirmed; reopen it first", code="script.confirmed")
    return page


def _after_orientation_change(
    db: Session, actor: User, page: Page, old: dict[str, object], action: str
) -> None:
    if page.effective_rotation != old["rotation"] and _has_model_read(db, page.id):
        page.rotated_after_transcription = True
    script = db.get(Script, page.script_id) if page.script_id else None
    if script is not None and is_reviewable(script):
        _touch(script)
    audit.record(
        db,
        actor=actor,
        entity_type="page",
        entity_id=page.id,
        action=action,
        old_value=old,
        new_value=_rotation_value(page),
    )


def set_rotation(db: Session, actor: User, page_id: int, rotation: int | None) -> None:
    """The teacher's rotate control (layer a). ``None`` resets to the automatic orientation.
    The stored image is never changed."""
    page = _page_for_orientation(db, actor, page_id)
    old = _rotation_value(page)
    if page.rotation_teacher == rotation:
        return
    page.rotation_teacher = rotation
    _after_orientation_change(db, actor, page, old, "rotate")


def undo_auto_rotation(db: Session, actor: User, page_id: int) -> None:
    page = _page_for_orientation(db, actor, page_id)
    if page.rotation_auto % 360 == 0:
        raise ConflictError("The page was not turned automatically", code="page.not_auto_rotated")
    old = _rotation_value(page)
    page.rotation_auto = 0
    _after_orientation_change(db, actor, page, old, "undo_auto_rotation")


def retranscribe_key(page_id: int, rotation: int) -> str:
    return f"transcribe-page:{page_id}:{rotation}"


def request_retranscription(db: Session, actor: User, page_id: int, settings: Settings) -> None:
    """Queue a fresh read of a page after its orientation was corrected. Never automatic."""
    page, script = _script_page(db, actor, page_id)
    _require_editable(script)
    if page.is_cover:
        raise ConflictError("Cover sheets are not transcribed", code="page.is_cover")
    jobs.enqueue(
        db,
        JobType.TRANSCRIBE_PAGE,
        {"page_id": page.id},
        retranscribe_key(page.id, page.effective_rotation),
        max_attempts=settings.job_max_attempts,
        requeue=True,
    )
    audit.record(
        db,
        actor=actor,
        entity_type="page",
        entity_id=page.id,
        action="request_transcription",
        new_value={"rotation": page.effective_rotation},
    )


# --- confirm and reopen -----------------------------------------------------------------------


def undecided_points(db: Session, script: Script) -> list[int]:
    decisions = current_decisions(db, [script.id])
    missing = []
    for question in exam_questions(db, script.exam_id):
        for point in question.points:
            d = decisions.get((script.id, point.id))
            if d is None or d.final_half_marks is None or d.final_category is None:
                missing.append(point.id)
    return missing


def confirm(db: Session, actor: User, script_id: int) -> None:
    from app.services.answer_sheets import require_complete

    script = _editable_script(db, actor, script_id)
    require_complete(db, script.exam_id, script.student_id)
    missing = undecided_points(db, script)
    if missing:
        raise ConflictError(
            "Every point needs a final mark and category before confirming",
            code="script.incomplete",
            issues=[Issue("script.point_undecided", ["points", p]) for p in missing],
        )
    now = utcnow()
    old_status = script.status
    script.status = ScriptStatus.CONFIRMED
    script.confirmed_by_id = actor.id
    script.confirmed_at = now
    session = _open_session(db, script.id, actor.id)
    if session is not None:
        _add_active_time(session, now)
        session.confirmed_at = now
    audit.record(
        db,
        actor=actor,
        entity_type="script",
        entity_id=script.id,
        action="confirm",
        old_value={"status": old_status.value},
        new_value={"status": script.status.value, "confirmed_at": now.isoformat()},
    )
    _update_exam_completion(db, actor, script.exam_id)


def reopen(db: Session, actor: User, script_id: int) -> None:
    script = get_visible_script(db, actor, script_id)
    if script.status != ScriptStatus.CONFIRMED:
        raise ConflictError("Script is not confirmed", code="script.not_confirmed")
    if any(
        script.id in job.script_ids
        for job in db.scalars(
            select(PrintJob).where(
                PrintJob.exam_id == script.exam_id, PrintJob.status == "submitting"
            )
        )
    ):
        raise ConflictError(
            "A print is being sent; wait for its status", code="hardware.print_busy"
        )
    old = {
        "status": script.status.value,
        "confirmed_at": script.confirmed_at.isoformat() if script.confirmed_at else None,
        "confirmed_by_id": script.confirmed_by_id,
    }
    script.status = ScriptStatus.IN_REVIEW
    script.confirmed_by_id = None
    script.confirmed_at = None
    audit.record(
        db,
        actor=actor,
        entity_type="script",
        entity_id=script.id,
        action="reopen",
        old_value=old,
        new_value={"status": script.status.value},
    )
    _update_exam_completion(db, actor, script.exam_id)


def _update_exam_completion(db: Session, actor: User, exam_id: int) -> None:
    """Phase 5: an exam is completed once every script is confirmed, and goes back to
    reviewing when one is reopened."""
    exam = db.get(Exam, exam_id)
    if exam is None or exam.status not in (ExamStatus.REVIEWING, ExamStatus.COMPLETED):
        return
    db.flush()
    statuses = set(db.scalars(select(Script.status).where(Script.exam_id == exam_id)))
    target = ExamStatus.COMPLETED if statuses == {ScriptStatus.CONFIRMED} else ExamStatus.REVIEWING
    if exam.status == target:
        return
    old = exam.status
    exam.status = target
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="set_status",
        old_value=old.value,
        new_value=target.value,
    )


# --- review time (owner change 2) -------------------------------------------------------------


def _open_session(db: Session, script_id: int, user_id: int) -> ReviewSession | None:
    return db.scalar(
        select(ReviewSession)
        .where(
            ReviewSession.script_id == script_id,
            ReviewSession.user_id == user_id,
            ReviewSession.confirmed_at.is_(None),
        )
        .order_by(ReviewSession.id.desc())
        .limit(1)
    )


def _add_active_time(session: ReviewSession, now: datetime) -> None:
    if session.last_heartbeat_at is not None:
        gap = now - session.last_heartbeat_at
        if timedelta(0) < gap <= IDLE_GAP:
            session.active_seconds += min(gap.total_seconds(), HEARTBEAT_MAX_SECONDS)
    session.last_heartbeat_at = now


def heartbeat(db: Session, actor: User, script_id: int) -> ReviewSession | None:
    """The review screen is open and in use. Opens a session on the first call; afterwards adds
    the time since the previous heartbeat (at most 60 s, nothing after an idle gap)."""
    script = get_visible_script(db, actor, script_id)
    if script.status == ScriptStatus.CONFIRMED or not is_reviewable(script):
        return None  # viewing a confirmed script is not review time
    now = utcnow()
    session = _open_session(db, script.id, actor.id)
    if session is None:
        session = ReviewSession(
            script_id=script.id,
            user_id=actor.id,
            opened_at=now,
            active_seconds=0.0,
            last_heartbeat_at=now,
        )
        db.add(session)
    else:
        _add_active_time(session, now)
    db.flush()
    return session


@dataclass(frozen=True)
class ReviewTime:
    wall_seconds: float
    active_seconds: float


def review_times(db: Session, script_ids: Iterable[int]) -> dict[int, ReviewTime]:
    """Per script, the sum of its finished sessions (opened to confirmed)."""
    ids = list(script_ids)
    if not ids:
        return {}
    wall: dict[int, float] = defaultdict(float)
    active: dict[int, float] = defaultdict(float)
    for session in db.scalars(
        select(ReviewSession).where(
            ReviewSession.script_id.in_(ids), ReviewSession.confirmed_at.is_not(None)
        )
    ):
        if session.confirmed_at is None:  # pragma: no cover - excluded by the query
            continue
        wall[session.script_id] += (session.confirmed_at - session.opened_at).total_seconds()
        active[session.script_id] += session.active_seconds
    return {i: ReviewTime(wall[i], active[i]) for i in wall}


# --- marking queue (screen 6) -----------------------------------------------------------------


@dataclass
class _Summary:
    min_confidence: float | None = None
    uncertain: int = 0
    deductions: int = 0
    deducted_half: int = 0
    decided: int = 0
    proposed_half: int | None = None
    final_half: int | None = None


def _summaries(
    db: Session, scripts: list[Script], questions: list[Question]
) -> dict[int, _Summary]:
    decisions = current_decisions(db, [s.id for s in scripts])
    out: dict[int, _Summary] = {}
    for script in scripts:
        summary = _Summary()
        for question in questions:
            proposed = final = None
            for point in question.points:
                d = decisions.get((script.id, point.id))
                if d is None:
                    if (point.rules or {}).get("teacher_only", False):
                        summary.min_confidence = 0.0
                        summary.uncertain += 1
                    continue
                if d.proposed_half_marks is not None:
                    proposed = (proposed or 0) + d.proposed_half_marks
                    if d.proposed_half_marks < point.half_marks:
                        summary.deductions += 1
                        summary.deducted_half += point.half_marks - d.proposed_half_marks
                if d.confidence is not None:
                    summary.min_confidence = min(
                        summary.min_confidence if summary.min_confidence is not None else 1.0,
                        d.confidence,
                    )
                if d.error_category == ErrorCategory.TRANSCRIPTION_UNCERTAIN:
                    summary.uncertain += 1
                if d.final_half_marks is not None:
                    final = (final or 0) + d.final_half_marks
                    if d.final_category is not None:
                        summary.decided += 1
            proposed = score_question(
                question,
                {
                    p.id: decisions[(script.id, p.id)].proposed_half_marks
                    if (script.id, p.id) in decisions
                    else None
                    for p in question.points
                },
            )
            final = score_question(
                question,
                {
                    p.id: decisions[(script.id, p.id)].final_half_marks
                    if (script.id, p.id) in decisions
                    else None
                    for p in question.points
                },
            )
            if proposed is not None:
                summary.proposed_half = (summary.proposed_half or 0) + min(
                    proposed, question.max_half_marks
                )
            if final is not None:
                summary.final_half = (summary.final_half or 0) + min(final, question.max_half_marks)
        out[script.id] = summary
    return out


def _marks(half: int | None) -> Marks | None:
    return None if half is None else from_half_marks(half)


def _queue_items(db: Session, exam: Exam) -> tuple[list[QueueItemOut], int | None]:
    from app.services import lifecycle

    scripts = list(db.scalars(select(Script).where(Script.exam_id == exam.id)))
    questions = exam_questions(db, exam.id)
    max_half = sum(q.max_half_marks for q in questions)
    total_points = sum(len(q.points) for q in questions)
    page_counts = dict(
        db.execute(
            select(Page.script_id, func.count())
            .where(Page.script_id.in_([s.id for s in scripts]), Page.state == PageState.ASSIGNED)
            .group_by(Page.script_id)
        ).all()
    )
    auto_rotated = dict(
        db.execute(
            select(Page.script_id, func.count())
            .where(
                Page.script_id.in_([s.id for s in scripts]),
                Page.state == PageState.ASSIGNED,
                Page.rotation_teacher.is_(None),
                Page.rotation_auto != 0,
            )
            .group_by(Page.script_id)
        ).all()
    )
    typical = typical_page_count([page_counts.get(s.id, 0) for s in scripts])
    summaries = _summaries(db, scripts, questions)
    times = review_times(db, [s.id for s in scripts])
    tested = test_model_scripts(db, [s.id for s in scripts])

    items = []
    for script in scripts:
        s = summaries[script.id]
        count = page_counts.get(script.id, 0)
        time = times.get(script.id)
        items.append(
            QueueItemOut(
                lifecycle=lifecycle.state(db, script),
                printed=lifecycle.printed(db, script),
                script_id=script.id,
                student_code=script.student.code,
                student_name=script.student.display_name,
                status=script.status,
                manual_reason=script.manual_reason,
                reviewable=is_reviewable(script),
                page_count=count,
                page_count_flag=page_count_flag(count, typical),
                auto_rotated_pages=auto_rotated.get(script.id, 0),
                min_confidence=s.min_confidence,
                uncertain_points=s.uncertain,
                deductions=s.deductions,
                marks_deducted=from_half_marks(s.deducted_half),
                decided_points=s.decided,
                total_points=total_points,
                proposed_total=_marks(s.proposed_half),
                final_total=_marks(s.final_half),
                max_total=from_half_marks(max_half),
                review_seconds=time.wall_seconds if time else None,
                active_seconds=time.active_seconds if time else None,
                test_model=script.id in tested,
            )
        )
    items.sort(key=_queue_order)
    return items, typical


def _queue_order(item: QueueItemOut) -> tuple[object, ...]:
    """Uncertainty first (Phase 4 plan): needs manual marking, then transcription-uncertain
    points, then lowest confidence, then a page-count flag, then the rest. Scripts the AI is
    still working on come next, confirmed scripts last."""
    if item.status == ScriptStatus.CONFIRMED:
        group = 2
    elif item.reviewable:
        group = 0
    else:
        group = 1
    return (
        group,
        item.manual_reason is None,
        item.uncertain_points == 0,
        item.min_confidence if item.min_confidence is not None else 1.0,
        item.page_count_flag is None,
        item.student_code,
    )


def queue(db: Session, actor: User, exam_id: int) -> QueueOut:
    exam = get_visible_exam(db, actor, exam_id)
    items, typical = _queue_items(db, exam)
    timed = [
        i for i in items if i.status == ScriptStatus.CONFIRMED and i.review_seconds is not None
    ]
    return QueueOut(
        exam_id=exam.id,
        exam_title=exam.title,
        exam_status=exam.status,
        items=items,
        typical_page_count=typical,
        confirmed_count=sum(1 for i in items if i.status == ScriptStatus.CONFIRMED),
        timed_count=len(timed),
        average_review_seconds=(
            sum(i.review_seconds or 0 for i in timed) / len(timed) if timed else None
        ),
        average_active_seconds=(
            sum(i.active_seconds or 0 for i in timed) / len(timed) if timed else None
        ),
        test_model_count=sum(1 for i in items if i.test_model),
    )


# --- script review (screen 7) -----------------------------------------------------------------


def _version_out(t: Transcription) -> TranscriptionVersionOut:
    return TranscriptionVersionOut(
        id=t.id,
        text=t.text,
        source=t.source,
        model_name=t.model_name,
        model_version=t.model_version,
        prompt_version=t.prompt_version,
        rotation=t.rotation,
        created_at=t.created_at,
    )


def _pending_reads(db: Session, pages: list[Page]) -> set[int]:
    keys = {retranscribe_key(p.id, p.effective_rotation): p.id for p in pages}
    if not keys:
        return set()
    rows = db.scalars(
        select(Job.idempotency_key).where(
            Job.idempotency_key.in_(keys),
            Job.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
        )
    )
    return {keys[k] for k in rows}


def script_review(db: Session, actor: User, script_id: int) -> ScriptReviewOut:
    script = get_visible_script(db, actor, script_id)
    exam = db.get(Exam, script.exam_id)
    if exam is None:  # pragma: no cover
        raise NotFoundError("Exam")
    questions = exam_questions(db, exam.id)
    decisions = current_decisions(db, [script.id])
    comments = {
        c.question_id: c.text
        for c in db.scalars(select(QuestionComment).where(QuestionComment.script_id == script.id))
    }
    proposed_times = [
        d.proposed_at
        for d in decisions.values()
        if d.proposed_half_marks is not None and d.proposed_at
    ]
    marked_at = min(proposed_times) if proposed_times else None

    pages = [p for p in script.pages if p.state == PageState.ASSIGNED]
    pending = _pending_reads(db, pages)
    page_out = []
    edited_after = False
    for page in pages:
        versions = transcripts.page_versions(db, page.id)
        now = transcripts.current(versions)
        # The current text is newer than the AI's proposals (a teacher edit or a fresh read).
        after = marked_at is not None and now is not None and now.created_at > marked_at
        edited_after = edited_after or after
        page_out.append(
            ReviewPageOut(
                id=page.id,
                position=page.position,
                is_cover=page.is_cover,
                width=page.width,
                height=page.height,
                rotation=page.effective_rotation,
                rotation_teacher=page.rotation_teacher,
                rotation_auto=page.rotation_auto,
                auto_rotated=page.auto_rotated,
                auto_rotation_confidence=page.auto_rotation_confidence,
                rotated_after_transcription=page.rotated_after_transcription,
                retranscribe_pending=page.id in pending,
                transcription=_version_out(now) if now else None,
                versions=[_version_out(v) for v in versions],
                edited_after_marking=after,
            )
        )

    question_out = []
    totals = _Summary()
    for question in questions:
        points = []
        proposed = final = None
        deductions = deducted = 0
        for point in question.points:
            d = decisions.get((script.id, point.id))
            proposal = d.proposed_half_marks if d else None
            cut = (
                point.half_marks - proposal
                if proposal is not None and proposal < point.half_marks
                else 0
            )
            if proposal is not None:
                proposed = (proposed or 0) + proposal
            if cut:
                deductions += 1
                deducted += cut
            if d is not None and d.final_half_marks is not None:
                final = (final or 0) + d.final_half_marks
                totals.decided += d.final_category is not None
            points.append(
                ReviewPointOut(
                    teacher_only=bool((point.rules or {}).get("teacher_only", False)),
                    id=point.id,
                    position=point.position,
                    description=point.description,
                    alternatives=list(point.alternatives or []),
                    max_marks=from_half_marks(point.half_marks),
                    decision_id=d.id if d else None,
                    proposed_marks=_marks(proposal),
                    evidence=d.evidence if d else "",
                    confidence=d.confidence if d else None,
                    error_category=d.error_category if d else None,
                    deducted=from_half_marks(cut),
                    final_marks=_marks(d.final_half_marks) if d else None,
                    final_category=d.final_category if d else None,
                    decided_at=d.decided_at if d else None,
                    model_name=d.model_name if d else None,
                    model_version=d.model_version if d else None,
                    prompt_version=d.prompt_version if d else None,
                )
            )
        proposed_capped = score_question(
            question,
            {
                p.id: decisions[(script.id, p.id)].proposed_half_marks
                if (script.id, p.id) in decisions
                else None
                for p in question.points
            },
        )
        final_capped = score_question(
            question,
            {
                p.id: decisions[(script.id, p.id)].final_half_marks
                if (script.id, p.id) in decisions
                else None
                for p in question.points
            },
        )
        if proposed_capped is not None:
            totals.proposed_half = (totals.proposed_half or 0) + proposed_capped
        if final_capped is not None:
            totals.final_half = (totals.final_half or 0) + final_capped
        totals.deductions += deductions
        totals.deducted_half += deducted
        question_out.append(
            ReviewQuestionOut(
                id=question.id,
                label=question.label,
                prompt_text=question.prompt_text,
                max_marks=from_half_marks(question.max_half_marks),
                points=points,
                comment=comments.get(question.id, ""),
                proposed_total=_marks(proposed_capped),
                final_total=_marks(final_capped),
                deductions=deductions,
                marks_deducted=from_half_marks(deducted),
            )
        )

    items, _typical = _queue_items(db, exam)
    order = [i.script_id for i in items if i.reviewable]
    position = order.index(script.id) if script.id in order else -1
    total_points = sum(len(q.points) for q in questions)
    ready = is_reviewable(script)
    locked = script.status == ScriptStatus.CONFIRMED
    return ScriptReviewOut(
        script=ReviewScriptOut(
            id=script.id,
            status=script.status,
            manual_reason=script.manual_reason,
            student_code=script.student.code,
            student_name=script.student.display_name,
            reviewed_at=script.reviewed_at,
            confirmed_at=script.confirmed_at,
        ),
        exam=ReviewExamOut(
            id=exam.id,
            title=exam.title,
            subject_code=exam.subject_code,
            show_scheme_to_students=exam.show_scheme_to_students,
        ),
        ready=ready,
        locked=locked,
        can_confirm=ready and not locked and totals.decided == total_points,
        pages=page_out,
        questions=question_out,
        totals=ReviewTotalsOut(
            max_total=from_half_marks(sum(q.max_half_marks for q in questions)),
            proposed_total=_marks(totals.proposed_half),
            final_total=_marks(totals.final_half),
            decided_points=totals.decided,
            total_points=total_points,
            deductions=totals.deductions,
            marks_deducted=from_half_marks(totals.deducted_half),
        ),
        navigation=ReviewNavigationOut(
            previous_id=order[position - 1] if position > 0 else None,
            next_id=order[position + 1] if 0 <= position < len(order) - 1 else None,
            position=position + 1,
            count=len(order),
        ),
        marked_on_earlier_text=edited_after,
        test_model=bool(test_model_scripts(db, [script.id])),
        ai_run=script.ai_run,
    )
