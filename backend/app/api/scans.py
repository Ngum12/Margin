"""Cover sheets, scanned uploads, scripts and the unassigned tray (screens 4 and 5)."""

import hashlib
import secrets
import unicodedata
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse, Response

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.db.models import Exam, Page, Student, User
from app.errors import NotFoundError, PayloadTooLargeError, ValidationFailedError
from app.schemas.scans import (
    AssignPagesIn,
    CoverSheetRowOut,
    PageIdsIn,
    PageOut,
    ScriptOut,
    ScriptsOut,
    StudentRef,
    UploadOut,
)
from app.services import cover_sheets
from app.services import uploads as upload_service
from app.services.access import visible_exams
from app.services.upload_processor import UploadProcessor

router = APIRouter(tags=["scans"])

_PDF_MAGIC = b"%PDF-"
_CHUNK = 1024 * 1024


# --- cover sheets -----------------------------------------------------------------------------


def _sheet_rows(rows: list[cover_sheets.SheetRow]) -> list[CoverSheetRowOut]:
    return [
        CoverSheetRowOut(
            student_id=r.student.id,
            code=r.student.code,
            display_name=r.student.display_name,
            has_sheet=r.has_sheet,
        )
        for r in rows
    ]


@router.get("/exams/{exam_id}/cover-sheets")
def list_cover_sheets(exam_id: int, db: DbSession, user: CurrentUser) -> list[CoverSheetRowOut]:
    return _sheet_rows(cover_sheets.list_sheets(db, user, exam_id))


@router.post("/exams/{exam_id}/cover-sheets")
def prepare_cover_sheets(exam_id: int, db: DbSession, user: CurrentUser) -> list[CoverSheetRowOut]:
    return _sheet_rows(cover_sheets.prepare_sheets(db, user, exam_id))


@router.get("/exams/{exam_id}/cover-sheets.pdf")
def download_cover_sheets(exam_id: int, db: DbSession, user: CurrentUser) -> Response:
    exam, pdf = cover_sheets.cover_sheets_pdf(db, user, exam_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cover-sheets-exam-{exam.id}.pdf"',
            "Cache-Control": "no-store",
        },
    )


# --- uploads ----------------------------------------------------------------------------------


def _safe_filename(raw: str | None) -> str:
    name = unquote(raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return (name or "scan.pdf")[:255]


@router.post("/exams/{exam_id}/uploads", status_code=202)
async def upload_scan(
    exam_id: int,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> UploadOut:
    """Receive one scanned PDF as a raw ``application/pdf`` body (D-027). The file is streamed to
    disk with a size limit and hashed on the way; processing starts after the response."""
    upload_service.check_can_upload(db, user, exam_id)
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/pdf":
        raise ValidationFailedError("Upload a PDF file", code="upload.not_pdf")
    limit = settings.max_upload_mb * 1024 * 1024
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise PayloadTooLargeError(f"Larger than {settings.max_upload_mb} MB")

    tmp_dir = settings.upload_dir / "incoming"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    temp = tmp_dir / f"{secrets.token_hex(16)}.part"
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with temp.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise PayloadTooLargeError(f"Larger than {settings.max_upload_mb} MB")
                if len(head) < 1024:
                    head += chunk[: 1024 - len(head)]
                digest.update(chunk)
                out.write(chunk)
        if _PDF_MAGIC not in head:
            raise ValidationFailedError("This file is not a PDF", code="upload.not_pdf")
    except Exception:
        temp.unlink(missing_ok=True)
        raise

    upload = upload_service.create_upload(
        db,
        user,
        exam_id,
        temp_file=temp,
        sha256=digest.hexdigest(),
        size_bytes=size,
        filename=_safe_filename(request.headers.get("x-filename")),
        settings=settings,
    )
    processor: UploadProcessor = request.app.state.upload_processor
    background.add_task(processor.submit, upload.id)
    return UploadOut.model_validate(upload)


@router.get("/exams/{exam_id}/uploads")
def list_uploads(exam_id: int, db: DbSession, user: CurrentUser) -> list[UploadOut]:
    return [UploadOut.model_validate(u) for u in upload_service.list_uploads(db, user, exam_id)]


@router.post("/uploads/{upload_id}/retry", status_code=202)
def retry_upload(
    upload_id: int,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
) -> UploadOut:
    upload = upload_service.retry_upload(db, user, upload_id)
    processor: UploadProcessor = request.app.state.upload_processor
    background.add_task(processor.submit, upload.id)
    return UploadOut.model_validate(upload)


def _data_file(settings_dir: Path, relative: str) -> Path:
    """Resolve a stored relative path; refuse anything outside the data folder."""
    base = settings_dir.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise NotFoundError("File")
    return path


@router.get("/uploads/{upload_id}/original")
def download_original(
    upload_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> FileResponse:
    upload = upload_service.get_visible_upload(db, user, upload_id)
    return FileResponse(
        _data_file(settings.data_dir, upload.stored_path),
        media_type="application/pdf",
        filename=upload.original_filename,
        headers={"Cache-Control": "private, no-store"},
    )


# --- pages, scripts and tray ------------------------------------------------------------------


@router.get("/pages/{page_id}/image")
def page_image(
    page_id: int,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    size: Literal["thumb", "full"] = "full",
) -> FileResponse:
    page = upload_service.get_visible_page(db, user, page_id)
    relative = page.thumb_path if size == "thumb" else page.image_path
    return FileResponse(
        _data_file(settings.data_dir, relative),
        media_type="image/jpeg",
        # Page images never change for a given page id.
        headers={"Cache-Control": "private, max-age=86400"},
    )


def _visible_exam_titles(db: DbSession, user: User, exam_ids: set[int]) -> dict[int, str]:
    if not exam_ids:
        return {}
    rows = db.scalars(visible_exams(user).where(Exam.id.in_(exam_ids)))
    return {e.id: e.title for e in rows}


def _page_out(page: Page, titles: dict[int, str]) -> PageOut:
    out = PageOut.model_validate(page)
    if page.detected_exam_id is not None:
        out.detected_exam_title = titles.get(page.detected_exam_id)
    return out


def _student_ref(student: Student) -> StudentRef:
    return StudentRef(id=student.id, code=student.code, display_name=student.display_name)


@router.get("/exams/{exam_id}/scripts")
def list_scripts(exam_id: int, db: DbSession, user: CurrentUser) -> ScriptsOut:
    scripts = upload_service.list_scripts(db, user, exam_id)
    missing = upload_service.students_without_scripts(db, user, exam_id)
    return ScriptsOut(
        scripts=[
            ScriptOut(
                id=s.id,
                student=_student_ref(s.student),
                status=s.status,
                pages=[_page_out(p, {}) for p in s.pages],
            )
            for s in scripts
        ],
        missing=[_student_ref(st) for st in missing],
    )


@router.get("/exams/{exam_id}/unassigned-pages")
def list_tray(exam_id: int, db: DbSession, user: CurrentUser) -> list[PageOut]:
    pages = upload_service.list_tray(db, user, exam_id)
    titles = _visible_exam_titles(
        db, user, {p.detected_exam_id for p in pages if p.detected_exam_id}
    )
    return [_page_out(p, titles) for p in pages]


@router.post("/exams/{exam_id}/pages/assign", status_code=204)
def assign_pages(exam_id: int, data: AssignPagesIn, db: DbSession, user: CurrentUser) -> None:
    upload_service.assign_pages(db, user, exam_id, data.page_ids, data.student_id)


@router.post("/exams/{exam_id}/pages/unassign", status_code=204)
def unassign_pages(exam_id: int, data: PageIdsIn, db: DbSession, user: CurrentUser) -> None:
    upload_service.unassign_pages(db, user, exam_id, data.page_ids)


@router.post("/exams/{exam_id}/pages/discard", status_code=204)
def discard_pages(exam_id: int, data: PageIdsIn, db: DbSession, user: CurrentUser) -> None:
    upload_service.discard_pages(db, user, exam_id, data.page_ids)
