"""Starting AI marking, building what the models see, and following progress."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.types import ExamSpec, PointSpec, QuestionSpec
from app.config import Settings
from app.db.models import (
    Exam,
    ExamStatus,
    Job,
    JobStatus,
    JobType,
    MarkDecision,
    Script,
    ScriptStatus,
    Transcription,
    User,
)
from app.errors import ConflictError
from app.marks import from_half_marks
from app.services import audit, jobs
from app.services.access import get_visible_exam, get_visible_script
from app.subjects.registry import get_registry


def transcribe_key(script_id: int) -> str:
    return f"transcribe:{script_id}"


def mark_key(script_id: int) -> str:
    return f"mark:{script_id}"


def exam_spec(exam: Exam, curriculum: str) -> ExamSpec:
    """What the Marker sees: subject, questions and mark scheme. No student information."""
    subject = get_registry().get(curriculum, exam.subject_code)
    if subject is None:  # pragma: no cover - validated when the exam was created
        raise ConflictError("Unknown subject", code="exam.subject_unknown")
    return ExamSpec(
        subject=subject,
        questions=tuple(
            QuestionSpec(
                id=q.id,
                label=q.label,
                prompt_text=q.prompt_text,
                max_marks=int(from_half_marks(q.max_half_marks)),
                points=tuple(
                    PointSpec(
                        id=p.id,
                        description=p.description,
                        marks=int(from_half_marks(p.half_marks)),
                        alternatives=tuple(p.alternatives),
                    )
                    for p in q.points
                ),
            )
            for q in exam.questions
        ),
    )


def _ai_in_progress(script: Script) -> bool:
    return script.manual_reason is None and script.status in (
        ScriptStatus.WAITING,
        ScriptStatus.TRANSCRIBED,
    )


def _rerun(db: Session, actor: User | None, script: Script, settings: Settings) -> None:
    """Start a new AI run for one script. Earlier proposals and decisions stay as history; the
    review shows only the new run. Pages are read again only by a different reader model or
    prompt (an unchanged reader reuses its reads, so a teacher's later edit is what is marked)."""
    old = {
        "ai_run": script.ai_run,
        "status": script.status.value,
        "manual_reason": script.manual_reason,
    }
    script.ai_run += 1
    script.status = ScriptStatus.WAITING
    script.manual_reason = None
    script.ai_started_at = None
    jobs.enqueue(
        db,
        JobType.TRANSCRIBE_SCRIPT,
        {"script_id": script.id},
        transcribe_key(script.id),
        max_attempts=settings.job_max_attempts,
        requeue=True,
    )
    audit.record(
        db,
        actor=actor,
        entity_type="script",
        entity_id=script.id,
        action="rerun_ai",
        old_value=old,
        new_value={"ai_run": script.ai_run, "status": script.status.value},
    )


def _require_rerunnable(script: Script) -> None:
    if script.status == ScriptStatus.CONFIRMED:
        raise ConflictError("Script is confirmed; reopen it first", code="script.confirmed")
    if _ai_in_progress(script):
        raise ConflictError("AI marking is still running for this script", code="ai.in_progress")


def _back_to_marking(exam: Exam) -> None:
    if exam.status in (ExamStatus.REVIEWING, ExamStatus.COMPLETED):
        exam.status = ExamStatus.MARKING


def rerun_script(db: Session, actor: User | None, script: Script, settings: Settings) -> None:
    """Re-run AI marking for one unconfirmed script (access already checked)."""
    _require_rerunnable(script)
    exam = db.get(Exam, script.exam_id)
    if exam is None:  # pragma: no cover
        raise ConflictError("Exam missing", code="conflict")
    _rerun(db, actor, script, settings)
    _back_to_marking(exam)


def rerun_visible_script(db: Session, actor: User, script_id: int, settings: Settings) -> None:
    rerun_script(db, actor, get_visible_script(db, actor, script_id), settings)


def rerun_exam(db: Session, actor: User | None, exam: Exam, settings: Settings) -> int:
    """Re-run AI marking for every unconfirmed script of an exam that the AI is not already
    working on. Confirmed scripts are never touched. Returns the number of scripts re-run."""
    scripts = [
        s
        for s in db.scalars(select(Script).where(Script.exam_id == exam.id).order_by(Script.id))
        if s.status != ScriptStatus.CONFIRMED and not _ai_in_progress(s)
    ]
    if not scripts:
        raise ConflictError("No unconfirmed scripts to re-run", code="ai.nothing_to_rerun")
    for script in scripts:
        _rerun(db, actor, script, settings)
    _back_to_marking(exam)
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="rerun_ai",
        new_value={"scripts": len(scripts)},
    )
    return len(scripts)


def rerun_visible_exam(db: Session, actor: User, exam_id: int, settings: Settings) -> int:
    return rerun_exam(db, actor, get_visible_exam(db, actor, exam_id), settings)


def start_ai_marking(db: Session, actor: User, exam_id: int, settings: Settings) -> int:
    """Queue transcription for every waiting script and re-queue failed AI jobs. Returns the
    number of scripts queued."""
    exam = get_visible_exam(db, actor, exam_id)
    if exam.status == ExamStatus.DRAFT:
        raise ConflictError("Mark the exam as ready first", code="exam.sheets_need_ready")
    scripts = db.scalars(select(Script).where(Script.exam_id == exam.id)).all()
    if not scripts:
        raise ConflictError("No scripts have been uploaded yet", code="ai.no_scripts")
    queued = 0
    for script in scripts:
        if script.manual_reason is not None:
            continue
        if script.status == ScriptStatus.WAITING:
            jobs.enqueue(
                db,
                JobType.TRANSCRIBE_SCRIPT,
                {"script_id": script.id},
                transcribe_key(script.id),
                max_attempts=settings.job_max_attempts,
                requeue=True,
            )
            queued += 1
        elif script.status == ScriptStatus.TRANSCRIBED:
            jobs.enqueue(
                db,
                JobType.MARK_SCRIPT,
                {"script_id": script.id},
                mark_key(script.id),
                max_attempts=settings.job_max_attempts,
                requeue=True,
            )
            queued += 1
    if exam.status == ExamStatus.READY:
        exam.status = ExamStatus.MARKING
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="start_ai_marking",
        new_value={"scripts_queued": queued},
    )
    return queued


def script_is_done(script: Script) -> bool:
    return script.manual_reason is not None or script.status not in (
        ScriptStatus.WAITING,
        ScriptStatus.TRANSCRIBED,
    )


def update_exam_progress(db: Session, exam_id: int) -> None:
    """Move the exam to "reviewing" once every script is AI-marked or flagged for manual marking."""
    exam = db.get(Exam, exam_id)
    if exam is None or exam.status != ExamStatus.MARKING:
        return
    scripts = db.scalars(select(Script).where(Script.exam_id == exam_id)).all()
    if scripts and all(script_is_done(s) for s in scripts):
        exam.status = ExamStatus.REVIEWING


@dataclass(frozen=True)
class AiStatus:
    by_status: dict[str, int]
    flagged: list[tuple[int, str, str]]  # (script id, student code, reason code)
    jobs_queued: int
    jobs_running: int
    jobs_failed: int


def ai_status(db: Session, actor: User, exam_id: int) -> AiStatus:
    exam = get_visible_exam(db, actor, exam_id)
    scripts = db.scalars(select(Script).where(Script.exam_id == exam.id)).all()
    by_status: dict[str, int] = {s.value: 0 for s in ScriptStatus}
    for script in scripts:
        by_status[script.status.value] += 1
    keys = [transcribe_key(s.id) for s in scripts] + [mark_key(s.id) for s in scripts]
    counts = (
        dict(
            db.execute(
                select(Job.status, func.count())
                .where(Job.idempotency_key.in_(keys))
                .group_by(Job.status)
            ).all()
        )
        if keys
        else {}
    )
    return AiStatus(
        by_status=by_status,
        flagged=[(s.id, s.student.code, s.manual_reason) for s in scripts if s.manual_reason],
        jobs_queued=counts.get(JobStatus.QUEUED, 0),
        jobs_running=counts.get(JobStatus.RUNNING, 0),
        jobs_failed=counts.get(JobStatus.FAILED, 0),
    )


@dataclass(frozen=True)
class ScriptAiResults:
    script: Script
    transcriptions: list[Transcription]
    decisions: list[MarkDecision]


def script_ai_results(db: Session, actor: User, script_id: int) -> ScriptAiResults:
    script = get_visible_script(db, actor, script_id)
    transcriptions = db.scalars(
        select(Transcription)
        .where(Transcription.script_id == script.id)
        .order_by(Transcription.page_id, Transcription.id)
    ).all()
    decisions = db.scalars(
        select(MarkDecision)
        .where(MarkDecision.script_id == script.id)
        .order_by(MarkDecision.mark_scheme_point_id, MarkDecision.id)
    ).all()
    return ScriptAiResults(script, list(transcriptions), list(decisions))
