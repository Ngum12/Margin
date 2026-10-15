"""Live AI progress for an exam (owner, 2026-10-15): how far the AI has got, what each script
is doing, the page being read, and an honest estimate of the time left.

Work is counted in units: one per answer page to read and one per question to mark, so the
bar moves every call rather than once per script. The time left uses the measured duration of
the recent calls on this machine; until a call of each needed kind has been measured, no
estimate is given rather than a guess.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Exam,
    Job,
    JobStatus,
    ModelCall,
    ModelRole,
    Page,
    PageState,
    Question,
    Script,
    ScriptStatus,
    Transcription,
    TranscriptionSource,
    User,
)
from app.services.access import get_visible_exam
from app.services.ai_marking import mark_key, transcribe_key

RECENT_CALLS = 20


@dataclass(frozen=True)
class ScriptProgress:
    script: Script
    step: str | None  # "reading" / "marking" while the worker is on it
    index: int | None
    total: int | None
    done_units: int
    total_units: int
    state: str  # "queued", "working", "ready", "manual", "confirmed", "idle"


@dataclass(frozen=True)
class LatestRead:
    page_id: int
    student_code: str
    text: str
    at: datetime


@dataclass(frozen=True)
class ExamProgress:
    exam: Exam
    scripts: list[ScriptProgress]
    done_units: int
    total_units: int
    running: bool
    eta_seconds: float | None
    current_page_id: int | None
    current_student: str | None
    latest_read: LatestRead | None

    @property
    def percent(self) -> int:
        if self.total_units == 0:
            return 100
        return min(100, round(100 * self.done_units / self.total_units))

    def count(self, state: str) -> int:
        return sum(1 for s in self.scripts if s.state == state)


def _average_seconds(db: Session, role: ModelRole) -> float | None:
    recent = list(
        db.scalars(
            select(ModelCall.seconds)
            .where(ModelCall.role == role)
            .order_by(ModelCall.id.desc())
            .limit(RECENT_CALLS)
        )
    )
    return sum(recent) / len(recent) if recent else None


def _script_progress(script: Script, pages: int, questions: int, has_job: bool) -> ScriptProgress:
    total = pages + questions
    done_ai = script.manual_reason is not None or script.status not in (
        ScriptStatus.WAITING,
        ScriptStatus.TRANSCRIBED,
    )
    if script.status == ScriptStatus.CONFIRMED:
        return ScriptProgress(script, None, None, None, total, total, "confirmed")
    if done_ai:
        state = "manual" if script.manual_reason else "ready"
        return ScriptProgress(script, None, None, None, total, total, state)
    step, index = script.ai_step, script.ai_step_index or 0
    if script.status == ScriptStatus.WAITING:
        done = max(index - 1, 0) if step == "reading" else 0
    else:  # transcribed: every page read, marking under way or queued
        done = pages + (max(index - 1, 0) if step == "marking" else 0)
    state = "working" if step else ("queued" if has_job else "idle")
    return ScriptProgress(
        script, step, script.ai_step_index, script.ai_step_total, done, total, state
    )


def exam_progress(db: Session, actor: User, exam_id: int) -> ExamProgress:
    exam = get_visible_exam(db, actor, exam_id)
    scripts = list(db.scalars(select(Script).where(Script.exam_id == exam.id)))
    scripts.sort(key=lambda s: s.student.code)
    questions = db.scalar(select(func.count()).where(Question.exam_id == exam.id)) or 0
    pages = dict(
        db.execute(
            select(Page.script_id, func.count())
            .where(
                Page.script_id.in_([s.id for s in scripts]),
                Page.state == PageState.ASSIGNED,
                Page.is_cover.is_(False),
            )
            .group_by(Page.script_id)
        ).all()
    )
    keys = {key(s.id): s.id for s in scripts for key in (transcribe_key, mark_key)}
    with_job = {
        keys[k]
        for k in db.scalars(
            select(Job.idempotency_key).where(
                Job.idempotency_key.in_(keys), Job.status.in_((JobStatus.QUEUED, JobStatus.RUNNING))
            )
        )
    }
    progress = [
        _script_progress(s, pages.get(s.id, 0), questions, s.id in with_job) for s in scripts
    ]
    running = any(p.state in ("working", "queued") for p in progress)
    # The run covers scripts the AI still has to finish plus those it has finished since.
    in_run = [p for p in progress if p.state != "confirmed"]
    done = sum(p.done_units for p in in_run)
    total = sum(p.total_units for p in in_run)

    eta: float | None = None
    if running:
        remaining_pages = sum(
            max(pages.get(p.script.id, 0) - p.done_units, 0)
            for p in in_run
            if p.script.status == ScriptStatus.WAITING and p.state in ("working", "queued")
        )
        remaining_questions = sum(
            p.total_units - max(p.done_units, pages.get(p.script.id, 0))
            for p in in_run
            if p.state in ("working", "queued")
        )
        read = _average_seconds(db, ModelRole.READER)
        mark = _average_seconds(db, ModelRole.MARKER)
        if (remaining_pages == 0 or read is not None) and (
            remaining_questions == 0 or mark is not None
        ):
            eta = remaining_pages * (read or 0) + remaining_questions * (mark or 0)

    current = next((p for p in progress if p.state == "working"), None)
    current_page = current.script.ai_step_page_id if current and current.step == "reading" else None
    latest = db.execute(
        select(Transcription, Script)
        .join(Script, Transcription.script_id == Script.id)
        .where(Script.exam_id == exam.id, Transcription.source == TranscriptionSource.MODEL)
        .order_by(Transcription.created_at.desc(), Transcription.id.desc())
        .limit(1)
    ).first()
    return ExamProgress(
        exam=exam,
        scripts=progress,
        done_units=done,
        total_units=total,
        running=running,
        eta_seconds=eta,
        current_page_id=current_page,
        current_student=current.script.student.code if current else None,
        latest_read=(
            LatestRead(
                latest[0].page_id, latest[1].student.code, latest[0].text, latest[0].created_at
            )
            if latest
            else None
        ),
    )
