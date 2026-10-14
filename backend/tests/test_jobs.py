from datetime import timedelta

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db.models import Job, JobStatus, JobType
from app.services import jobs


def _job(db: Session, key: str = "k1", max_attempts: int = 3) -> Job:
    job = jobs.enqueue(db, JobType.MARK_SCRIPT, {"script_id": 1}, key, max_attempts=max_attempts)
    db.commit()
    return job


def test_enqueue_is_idempotent(db: Session) -> None:
    first = _job(db)
    second = jobs.enqueue(db, JobType.MARK_SCRIPT, {"script_id": 1}, "k1", max_attempts=3)

    assert first.id == second.id
    assert len(db.scalars(select(Job)).all()) == 1


def test_requeue_resets_a_failed_job(db: Session) -> None:
    job = _job(db)
    job.status, job.attempts, job.last_error = JobStatus.FAILED, 3, "boom"
    db.commit()

    again = jobs.enqueue(db, JobType.MARK_SCRIPT, {}, "k1", max_attempts=3, requeue=True)

    assert (again.status, again.attempts, again.last_error) == (JobStatus.QUEUED, 0, None)


def test_a_job_can_only_be_claimed_once(app: FastAPI, db: Session) -> None:
    _job(db)
    with app.state.sessionmaker() as a, app.state.sessionmaker() as b:
        first = jobs.claim_next(a, "worker-a")
        second = jobs.claim_next(b, "worker-b")

    assert first is not None
    assert second is None
    assert (first.status, first.attempts, first.locked_by) == (JobStatus.RUNNING, 1, "worker-a")


def test_future_jobs_are_not_claimed(db: Session) -> None:
    job = _job(db)
    job.run_after = utcnow() + timedelta(minutes=5)
    db.commit()

    assert jobs.claim_next(db, "w") is None


def test_failed_attempt_backs_off_then_fails_for_good(db: Session) -> None:
    _job(db, max_attempts=2)
    job = jobs.claim_next(db, "w")
    assert job is not None

    jobs.retry_or_fail(db, job, "model_unavailable: ConnectionRefusedError")
    db.commit()
    assert job.status == JobStatus.QUEUED
    assert job.run_after > utcnow() + timedelta(seconds=20)

    job.run_after = utcnow()
    db.commit()
    job = jobs.claim_next(db, "w")
    assert job is not None
    jobs.retry_or_fail(db, job, "model_unavailable")
    db.commit()
    assert job.status == JobStatus.FAILED
    assert job.attempts == 2


def test_stale_running_jobs_are_requeued(db: Session) -> None:
    _job(db, "stale")
    _job(db, "fresh")
    stale = jobs.claim_next(db, "dead-worker")
    fresh = jobs.claim_next(db, "live-worker")
    assert stale is not None
    assert fresh is not None
    stale.heartbeat_at = utcnow() - timedelta(minutes=10)
    db.commit()

    requeued = jobs.requeue_stale(db, timedelta(minutes=2))
    db.commit()

    assert requeued == [stale.id]
    assert stale.status == JobStatus.QUEUED
    assert fresh.status == JobStatus.RUNNING


def test_job_payloads_hold_ids_only(db: Session) -> None:
    job = _job(db)

    assert set(job.payload) == {"script_id"}
