"""Runs upload processing off the request path, one upload at a time.

Phase 2 keeps this in the web process (a single background thread that starts the render child
process). On start-up, uploads left pending or processing by a restart or power cut are queued
again; processing is idempotent. Phase 3 moves this onto the database job table and worker.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services import uploads

logger = logging.getLogger(__name__)


class UploadProcessor:
    def __init__(
        self, factory: sessionmaker[Session], settings: Settings, *, inline: bool = False
    ) -> None:
        self._factory = factory
        self._settings = settings
        # Inline mode (tests) processes immediately in the calling thread.
        self._inline = inline
        self._executor: ThreadPoolExecutor | None = None

    def submit(self, upload_id: int) -> None:
        if self._inline:
            self._run(upload_id)
            return
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uploads")
        self._executor.submit(self._run, upload_id)

    def _run(self, upload_id: int) -> None:
        try:
            uploads.process_upload(self._factory, self._settings, upload_id)
        except Exception:
            # Never leave an upload stuck in "processing" because of a bug: fail it visibly.
            logger.exception("Unexpected error while processing upload %s", upload_id)
            uploads.mark_failed_unexpectedly(self._factory, upload_id)

    def recover(self) -> None:
        """Queue uploads interrupted by a restart."""
        try:
            with self._factory() as db:
                pending = uploads.unfinished_upload_ids(db)
        except OperationalError:
            logger.warning("Database not initialised; skipping upload recovery")
            return
        for upload_id in pending:
            logger.info("Resuming interrupted upload %s", upload_id)
            self.submit(upload_id)

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
