"""Automatic eligibility checks; the durable queue remains the only work scheduler."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Exam, ExamStatus, Job, JobType, PageState, Script, ScriptStatus
from app.services import audit, jobs
from app.services.ai_marking import transcribe_key
from app.services.answer_sheets import readiness


def eligible(db: Session, exam: Exam, script: Script) -> bool:
    if exam.status == ExamStatus.DRAFT or script.manual_reason:
        return False
    pages = [p for p in script.pages if p.state == PageState.ASSIGNED and not p.is_cover]
    if not pages:
        return False
    missing, problems = readiness(db, exam.id, script.student_id)
    if missing or problems:
        return False
    # Per-page QR fixes orientation. Plain cover-sheet answers still need the teacher's check.
    return exam.pages_checked_at is not None or all(p.answer_sheet_id is not None for p in pages)


def tick(factory: sessionmaker[Session], settings: Settings) -> int:
    queued = 0
    with factory() as db:
        candidates = db.scalars(
            select(Script)
            .join(Exam)
            .where(Exam.auto_start_marking.is_(True), Script.status == ScriptStatus.WAITING)
        )
        for script in candidates:
            exam = db.get_one(Exam, script.exam_id)
            if not eligible(db, exam, script):
                continue
            if db.scalar(select(Job.id).where(Job.idempotency_key == transcribe_key(script.id))):
                continue
            job = jobs.enqueue(
                db,
                JobType.TRANSCRIBE_SCRIPT,
                {"script_id": script.id},
                transcribe_key(script.id),
                max_attempts=settings.job_max_attempts,
            )
            if job.attempts == 0:
                queued += 1
            if exam.status == ExamStatus.READY:
                exam.status = ExamStatus.MARKING
                audit.record(
                    db,
                    actor=None,
                    entity_type="exam",
                    entity_id=exam.id,
                    action="automatic_marking_started",
                )
        db.commit()
    return queued
