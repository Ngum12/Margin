"""The background worker: polls the job table and runs one job at a time."""

import logging
import os
import socket
import threading
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.types import ModelUnavailableError
from app.clock import utcnow
from app.config import Settings
from app.db.models import Job, WorkerHeartbeat
from app.services import jobs
from app.worker.handlers import HANDLERS

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, factory: sessionmaker[Session], settings: Settings) -> None:
        self._factory = factory
        self._settings = settings
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._current_job: int | None = None
        self._stop = threading.Event()
        self._started_at = utcnow()

    # --- heartbeat -----------------------------------------------------------------------------

    def beat(self) -> None:
        """Record that this worker is alive, and keep the current job's lease fresh."""
        now = utcnow()
        with self._factory() as db:
            row = db.scalar(
                select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == self.worker_id)
            )
            if row is None:
                db.add(
                    WorkerHeartbeat(
                        worker_id=self.worker_id, started_at=self._started_at, seen_at=now
                    )
                )
            else:
                row.seen_at = now
            if self._current_job is not None:
                job = db.get(Job, self._current_job)
                if job is not None and job.locked_by == self.worker_id:
                    job.heartbeat_at = now
            db.commit()

    @property
    def heartbeat_seconds(self) -> float:
        return max(0.5, min(15.0, self._settings.job_stale_seconds / 3))

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                self.beat()
            except Exception:  # pragma: no cover - keep beating through transient DB errors
                logger.exception("Heartbeat failed")

    # --- running jobs --------------------------------------------------------------------------

    def recover(self) -> None:
        with self._factory() as db:
            stale = jobs.requeue_stale(db, timedelta(seconds=self._settings.job_stale_seconds))
            db.commit()
        if stale:
            logger.info("Re-queued %s job(s) left running by a stopped worker", len(stale))

    def run_once(self) -> bool:
        """Run the next due job. Returns False when there was nothing to do."""
        with self._factory() as db:
            job = jobs.claim_next(db, self.worker_id)
            if job is None:
                return False
            job_id, job_type, payload = job.id, job.type, dict(job.payload)
        self._current_job = job_id
        logger.info("Job %s (%s) started", job_id, job_type.value)
        error: str | None = None
        try:
            HANDLERS[job_type](self._factory, self._settings, payload)
        except ModelUnavailableError as exc:
            error = f"model_unavailable: {exc}"
        except Exception as exc:
            logger.exception("Job %s (%s) raised", job_id, job_type.value)
            error = f"error: {type(exc).__name__}"
        finally:
            self._current_job = None
        with self._factory() as db:
            job = db.get(Job, job_id)
            if job is not None:
                if error is None:
                    jobs.complete(db, job)
                else:
                    jobs.retry_or_fail(db, job, error)
                db.commit()
        logger.info("Job %s finished: %s", job_id, error or "ok")
        return True

    def run_until_idle(self, max_jobs: int = 10_000) -> int:
        """Run due jobs until none is left (tests, demos)."""
        count = 0
        while count < max_jobs and self.run_once():
            count += 1
        return count

    def run_forever(self) -> None:
        self.recover()
        self.beat()
        heartbeat = threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True)
        heartbeat.start()
        logger.info("Worker %s started", self.worker_id)
        try:
            while not self._stop.is_set():
                if not self.run_once():
                    # Idle: pick up work abandoned by a worker that died meanwhile, then wait.
                    self.recover()
                    self._stop.wait(self._settings.worker_poll_seconds)
        finally:
            self._stop.set()

    def stop(self) -> None:
        self._stop.set()
