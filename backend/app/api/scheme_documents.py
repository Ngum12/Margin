"""Authenticated originals, extraction previews and school-shared schemes."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.db.models import Job, JobType, SchemeDocument, SchemeLibrary
from app.errors import NotFoundError, PayloadTooLargeError
from app.schemas.common import ApiModel
from app.schemas.mark_scheme import MarkSchemeIn
from app.security_headers import CONTENT_SECURITY_POLICY
from app.services import jobs
from app.services import scheme_documents as service
from app.services.access import get_visible_exam

router = APIRouter(tags=["scheme-documents"])


def output(db: DbSession, item: SchemeDocument) -> dict[str, Any]:
    job = db.scalar(select(Job).where(Job.idempotency_key == f"scheme:{item.id}"))
    return {
        "id": item.id,
        "kind": item.kind,
        "suffix": item.suffix,
        "status": job.status.value if job and item.status == "queued" else item.status,
        "text": item.text,
        "proposal": item.proposal,
        "error": item.error,
        "model_name": item.model_name,
        "model_version": item.model_version,
        "prompt_version": item.prompt_version,
    }


@router.get("/exams/{exam_id}/scheme-documents")
def documents(exam_id: int, db: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    get_visible_exam(db, user, exam_id)
    return [
        output(db, item)
        for item in db.scalars(
            select(SchemeDocument)
            .where(SchemeDocument.exam_id == exam_id)
            .order_by(SchemeDocument.id.desc())
        )
    ]


@router.post("/exams/{exam_id}/scheme-documents", status_code=202)
async def receive(
    exam_id: int,
    suffix: str,
    kind: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> dict[str, Any]:
    get_visible_exam(db, user, exam_id)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > service.MAX_BYTES:
            raise PayloadTooLargeError("Document exceeds limit")
    return output(
        db, service.receive(db, user, settings, exam_id, suffix.lower(), kind, bytes(body))
    )


@router.get("/scheme-documents/{document_id}/original")
def original(
    document_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> FileResponse:
    item = service.visible(db, user, document_id)
    types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".txt": "text/plain; charset=utf-8",
    }
    return FileResponse(
        settings.data_dir / item.file_path,
        media_type=types.get(item.suffix, "application/octet-stream"),
        headers={
            "Content-Security-Policy": CONTENT_SECURITY_POLICY.replace(
                "frame-ancestors 'none'", "frame-ancestors 'self'"
            ),
            "X-Frame-Options": "SAMEORIGIN",
        },
        filename="original" + item.suffix,
        content_disposition_type="inline" if item.suffix in types else "attachment",
    )


@router.get("/scheme-library")
def library(db: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    return [
        {"id": item.id, "title": item.title, "subject_code": item.subject_code}
        for item in db.scalars(
            select(SchemeLibrary)
            .where(SchemeLibrary.school_id == user.school_id)
            .order_by(SchemeLibrary.id.desc())
        )
    ]


class SaveIn(ApiModel):
    exam_id: int


@router.post("/scheme-library", status_code=201)
def save(data: SaveIn, db: DbSession, user: CurrentUser) -> dict[str, int]:
    return {"id": service.save_library(db, user, data.exam_id).id}


@router.get("/scheme-library/{entry_id}")
def load(entry_id: int, db: DbSession, user: CurrentUser) -> MarkSchemeIn:
    entry = db.get(SchemeLibrary, entry_id)
    if entry is None or entry.school_id != user.school_id:
        raise NotFoundError()
    return MarkSchemeIn.model_validate(entry.scheme)


@router.post("/scheme-documents/{document_id}/retry")
def retry(
    document_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> dict[str, Any]:
    item = service.visible(db, user, document_id)
    if item.status != "ready":
        jobs.enqueue(
            db,
            JobType.EXTRACT_SCHEME,
            {"document_id": item.id},
            f"scheme:{item.id}",
            max_attempts=settings.job_max_attempts,
            requeue=True,
        )
        item.status, item.error = "queued", None
    return output(db, item)
