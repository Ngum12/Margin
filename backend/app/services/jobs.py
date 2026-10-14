"""Durable job queue on the database (brief section 3: no Redis, survives restarts).

- ``enqueue`` is idempotent: the idempotency key is unique.
- ``claim_next`` takes a job with a conditional UPDATE, so two workers can never run the same job.
- Failed attempts are retried with exponential backoff up to ``max_attempts``.
- Jobs left "running" by a worker that died (stale heartbeat) are put back in the queue.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db.models import Job, JobStatus, JobType

BACKOFF_BASE = timedelta(seconds=30)
BACKOFF_MAX = timedelta(minutes=15)


def enqueue(
    db: Session,
    job_type: JobType,
    payload: dict[str, Any],
    key: str,
    *,
    max_attempts: int,
    requeue: bool = False,
) -> Job:
    """Add a job unless one with ``key`` exists. With ``requeue``, a finished or failed job with
    that key is reset to run again (an explicit retry)."""
    existing = db.scalar(select(Job).where(Job.idempotency_key == key))
    if existing is not None:
        if requeue and existing.status in (JobStatus.FAILED, JobStatus.SUCCEEDED):
            existing.status = JobStatus.QUEUED
            existing.attempts = 0
            existing.run_after = utcnow()
            existing.last_error = None
            existing.finished_at = None
        return existing
    job = Job(
        type=job_type,
        payload=payload,
        status=JobStatus.QUEUED,
        idempotency_key=key,
        attempts=0,
        max_attempts=max_attempts,
        run_after=utcnow(),
    )
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session, worker_id: str, now: datetime | None = None) -> Job | None:
    now = now or utcnow()
    candidates = db.scalars(
        select(Job.id)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= now)
        .order_by(Job.id)
        .limit(5)
    ).all()
    for job_id in candidates:
        claimed = cast(
            CursorResult[Any],
            db.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
                .values(
                    status=JobStatus.RUNNING,
                    locked_by=worker_id,
                    heartbeat_at=now,
                    started_at=now,
                    attempts=Job.attempts + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        db.commit()
        if claimed.rowcount == 1:
            job = db.get(Job, job_id)
            if job is not None:
                db.refresh(job)
                return job
    return None


def complete(db: Session, job: Job) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = utcnow()
    job.locked_by = None
    job.last_error = None


def retry_or_fail(db: Session, job: Job, error: str) -> None:
    """Record a failed attempt: back off and retry, or give up after ``max_attempts``."""
    job.last_error = error[:300]
    job.locked_by = None
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.finished_at = utcnow()
        return
    delay = min(BACKOFF_BASE * (2 ** (job.attempts - 1)), BACKOFF_MAX)
    job.status = JobStatus.QUEUED
    job.run_after = utcnow() + delay


def requeue_stale(db: Session, stale_after: timedelta, now: datetime | None = None) -> list[int]:
    """Put back jobs whose worker stopped heartbeating (crash, power cut, killed process)."""
    now = now or utcnow()
    stale = db.scalars(
        select(Job).where(
            Job.status == JobStatus.RUNNING,
            (Job.heartbeat_at.is_(None)) | (Job.heartbeat_at < now - stale_after),
        )
    ).all()
    for job in stale:
        job.status = JobStatus.QUEUED
        job.locked_by = None
        job.run_after = now
        job.last_error = "worker_stopped"
    return [j.id for j in stale]
