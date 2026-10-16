"""Photo capture with authenticated preparation previews and explicit acceptance."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import Field, model_validator
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.db.models import ScanBatch
from app.errors import ConflictError, PayloadTooLargeError
from app.schemas.common import ApiModel
from app.services import audit, capture

router = APIRouter(tags=["capture"])


class Options(ApiModel):
    left: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    top: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    right: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    bottom: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    angle: float = Field(default=0, ge=-15, le=15, allow_inf_nan=False)
    auto_crop: bool = True
    auto_straighten: bool = True
    clean: bool = True

    @model_validator(mode="after")
    def valid_box(self) -> "Options":
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("invalid_crop_rectangle")
        return self


def output(batch: ScanBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "status": batch.status,
        "error_code": batch.error_code,
        "options": batch.capture_options,
        "prepared": bool(batch.prepared_path),
    }


@router.get("/capture")
def listing(db: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    return [
        output(b)
        for b in db.scalars(
            select(ScanBatch)
            .where(ScanBatch.school_id == user.school_id, ScanBatch.captured_by_id == user.id)
            .order_by(ScanBatch.id.desc())
            .limit(50)
        )
    ]


@router.post("/capture", status_code=202)
async def receive(
    suffix: str, request: Request, db: DbSession, user: CurrentUser, settings: AppSettings
) -> dict[str, Any]:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > capture.MAX_BYTES:
            raise PayloadTooLargeError("Photo too large")
    return output(
        capture.receive(db, user, settings, bytes(body), suffix.lower(), Options().model_dump())
    )


@router.get("/capture/{batch_id}/image")
def image(
    batch_id: int, db: DbSession, user: CurrentUser, settings: AppSettings, original: bool = False
) -> FileResponse:
    batch = capture.visible(db, user, batch_id)
    if not batch.prepared_path:
        raise ConflictError("Preparation is not finished", code="capture.not_ready")
    # Serve an EXIF-normalised PNG preview; immutable original bytes remain in the archive.
    relative = Path(batch.prepared_path)
    if original:
        relative = relative.with_name("original-preview.png")
    return FileResponse(
        settings.data_dir / relative, media_type="image/png", headers={"Cache-Control": "no-store"}
    )


@router.put("/capture/{batch_id}/options", status_code=202)
def adjust(batch_id: int, body: Options, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    batch = capture.visible(db, user, batch_id)
    if batch.status not in {"capture_preview", "quarantine"}:
        raise ConflictError("Page cannot be edited now", code="capture.not_ready")
    batch.capture_options = body.model_dump()
    batch.status = "capture_preparing"
    batch.error_code = None
    audit.record(
        db,
        actor=user,
        entity_type="scan_batch",
        entity_id=batch.id,
        action="adjust_photo",
        new_value=body.model_dump(),
    )
    return output(batch)


@router.post("/capture/{batch_id}/accept")
def accept(batch_id: int, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    batch = capture.visible(db, user, batch_id)
    if batch.status == "capture_preview":
        batch.status = "pending"
        audit.record(
            db, actor=user, entity_type="scan_batch", entity_id=batch.id, action="accept_photo"
        )
    elif batch.status not in {"pending", "processed", "duplicate"}:
        raise ConflictError("Preview the prepared photo first", code="capture.not_ready")
    return output(batch)


@router.post("/capture/{batch_id}/discard", status_code=204)
def discard(batch_id: int, db: DbSession, user: CurrentUser) -> None:
    batch = capture.visible(db, user, batch_id)
    if batch.status not in {"capture_preview", "quarantine"}:
        raise ConflictError("Page has already entered intake", code="capture.not_ready")
    batch.status = "removed"
    audit.record(
        db, actor=user, entity_type="scan_batch", entity_id=batch.id, action="discard_photo"
    )
