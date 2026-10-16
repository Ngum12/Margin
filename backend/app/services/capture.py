"""Phone originals remain immutable; teachers approve the prepared page before routing."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import ScanBatch, User
from app.errors import ConflictError, NotFoundError, ValidationFailedError
from app.pdf.runner import BACKEND_DIR
from app.services import audit

MAX_BYTES = 20 * 1024 * 1024


def visible(db: Session, actor: User, batch_id: int) -> ScanBatch:
    batch = db.get(ScanBatch, batch_id)
    if (
        batch is None
        or batch.school_id != actor.school_id
        or batch.captured_by_id is None
        or (not actor.is_admin and batch.captured_by_id != actor.id)
    ):
        raise NotFoundError()
    return batch


def receive(
    db: Session, actor: User, settings: Settings, body: bytes, suffix: str, options: dict[str, Any]
) -> ScanBatch:
    if suffix not in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}:
        raise ValidationFailedError("Unsupported photograph", code="capture.image_type")
    if not body or len(body) > MAX_BYTES:
        raise ValidationFailedError("Photograph is empty or too large", code="capture.image_size")
    digest = hashlib.sha256(body).hexdigest()
    existing = db.scalar(
        select(ScanBatch).where(ScanBatch.school_id == actor.school_id, ScanBatch.sha256 == digest)
    )
    if existing:
        if existing.captured_by_id != actor.id:
            raise ConflictError("Already received", code="capture.duplicate")
        return existing
    relative = Path("scan-archive") / str(actor.school_id) / (digest + suffix)
    path = settings.data_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    batch = ScanBatch(
        school_id=actor.school_id,
        sha256=digest,
        size_bytes=len(body),
        source_name="phone" + suffix,
        stored_path=relative.as_posix(),
        captured_by_id=actor.id,
        capture_options=options,
        status="capture_preparing",
    )
    db.add(batch)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity_type="scan_batch",
        entity_id=batch.id,
        action="phone_capture",
        new_value={"hash": digest},
    )
    return batch


def prepare(factory: sessionmaker[Session], settings: Settings) -> None:
    with factory() as db:
        batch = db.scalar(
            select(ScanBatch)
            .where(ScanBatch.status == "capture_preparing")
            .order_by(ScanBatch.id)
            .limit(1)
        )
        if batch is None:
            return
        folder = settings.data_dir / "phone-pages" / str(batch.id)
        folder.mkdir(parents=True, exist_ok=True)
        options = folder / "options.json"
        options.write_text(json.dumps(batch.capture_options or {}), encoding="utf-8")
        target = folder / "prepared.png"
        try:
            result = subprocess.run(  # noqa: S603 - fixed interpreter/module, no shell
                [
                    sys.executable,
                    "-m",
                    "app.pdf.capture_worker",
                    "--input",
                    str(settings.data_dir / batch.stored_path),
                    "--output",
                    str(target),
                    "--options",
                    str(options),
                ],
                cwd=BACKEND_DIR,
                capture_output=True,
                timeout=settings.render_timeout_seconds,
                check=False,
            )
            if result.returncode != 0:
                raise ValueError("image_unreadable")
            batch.prepared_path = target.relative_to(settings.data_dir).as_posix()
            batch.status = "capture_preview"
            batch.error_code = None
        except (ValueError, subprocess.TimeoutExpired):
            batch.status = "quarantine"
            batch.error_code = "capture.image_unreadable"
        db.commit()
