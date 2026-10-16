"""Visible script states; printing is deliberately independent of marking status."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Exam,
    Job,
    JobStatus,
    PageState,
    PrintJob,
    RemarkRequest,
    Script,
    ScriptStatus,
)
from app.services.answer_sheets import readiness


def state(db: Session, script: Script) -> str:
    if db.scalar(
        select(RemarkRequest.id)
        .where(RemarkRequest.script_id == script.id, RemarkRequest.status != "answered")
        .limit(1)
    ):
        return "remark_requested"
    if script.status == ScriptStatus.CONFIRMED:
        exam = db.get(Exam, script.exam_id)
        return "released" if exam and exam.released_at else "confirmed"
    missing, problems = readiness(db, script.exam_id, script.student_id)
    if missing or problems or script.manual_reason:
        return "needs_attention"
    if script.status in (ScriptStatus.AI_MARKED, ScriptStatus.IN_REVIEW):
        return "ready_for_review"
    if db.scalar(
        select(Job.id)
        .where(
            Job.idempotency_key.in_([f"transcribe:{script.id}", f"mark:{script.id}"]),
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .limit(1)
    ):
        return "marking"
    return (
        "scanned" if any(p.state == PageState.ASSIGNED for p in script.pages) else "awaiting_scan"
    )


def printed(db: Session, script: Script) -> bool:
    if script.confirmed_at is None:
        return False
    return any(
        str(script.id) in job.confirmation_versions
        and job.confirmation_versions[str(script.id)] == script.confirmed_at.isoformat()
        for job in db.scalars(
            select(PrintJob).where(PrintJob.exam_id == script.exam_id, PrintJob.status == "printed")
        )
    )
