"""Scanned uploads: store the original, process it into pages and scripts, and manage the tray.

- The original PDF is kept byte-for-byte with its SHA-256 (D-030).
- Rendering runs in a child process (app.pdf.runner, D-028).
- Processing is idempotent: all page and script rows for an upload are written in one
  transaction, replacing any earlier attempt for that upload.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.clock import utcnow
from app.config import Settings
from app.db.models import (
    CoverSheet,
    Exam,
    ExamStatus,
    JobType,
    Page,
    PageState,
    Script,
    ScriptStatus,
    Student,
    UnassignedReason,
    Upload,
    UploadStatus,
    User,
)
from app.errors import ConflictError, NotFoundError
from app.pdf.runner import RenderError, render_pdf
from app.services import audit, jobs, page_check
from app.services.access import get_visible_exam, visible_exams
from app.services.splitting import SheetOwner, place_pages

logger = logging.getLogger(__name__)

ORIGINAL_NAME = "original.pdf"


def upload_folder(upload_id: int) -> Path:
    """Relative to MARGIN_DATA_DIR."""
    return Path("uploads") / str(upload_id)


# --- receiving --------------------------------------------------------------------------------


def check_can_upload(db: Session, actor: User, exam_id: int) -> Exam:
    exam = get_visible_exam(db, actor, exam_id)
    if exam.status == ExamStatus.DRAFT:
        raise ConflictError(
            "Mark the exam as ready before uploading scans", code="exam.sheets_need_ready"
        )
    return exam


def create_upload(
    db: Session,
    actor: User,
    exam_id: int,
    *,
    temp_file: Path,
    sha256: str,
    size_bytes: int,
    filename: str,
    settings: Settings,
) -> Upload:
    """Register a streamed PDF and move it into place. Deletes ``temp_file`` on any refusal."""
    try:
        exam = check_can_upload(db, actor, exam_id)
        duplicate = db.scalar(
            select(Upload.id).where(Upload.exam_id == exam.id, Upload.sha256 == sha256)
        )
        if duplicate is not None:
            raise ConflictError(
                "This exact file was already uploaded for this exam", code="upload.duplicate_file"
            )
        upload = Upload(
            exam_id=exam.id,
            uploaded_by_id=actor.id,
            original_filename=filename,
            stored_path="",
            sha256=sha256,
            size_bytes=size_bytes,
            status=UploadStatus.PENDING,
        )
        db.add(upload)
        db.flush()
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise

    relative = upload_folder(upload.id) / ORIGINAL_NAME
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_file.replace(target)
    upload.stored_path = relative.as_posix()
    jobs.enqueue(
        db,
        JobType.PROCESS_UPLOAD,
        {"upload_id": upload.id},
        f"upload:{upload.id}",
        max_attempts=settings.job_max_attempts,
    )
    audit.record(
        db,
        actor=actor,
        entity_type="upload",
        entity_id=upload.id,
        action="create",
        new_value={
            "exam_id": exam.id,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "filename": filename,
        },
    )
    return upload


# --- processing -------------------------------------------------------------------------------


def _students_with_pages(db: Session, exam_id: int, excluding_upload: int) -> set[int]:
    rows = db.scalars(
        select(Script.student_id)
        .join(Page, Page.script_id == Script.id)
        .where(Script.exam_id == exam_id, Page.upload_id != excluding_upload)
        .distinct()
    )
    return set(rows)


def _clear_previous_attempt(db: Session, upload: Upload) -> None:
    """Remove page rows from an earlier attempt, and scripts left with no pages."""
    script_ids = set(
        db.scalars(
            select(Page.script_id).where(Page.upload_id == upload.id, Page.script_id.is_not(None))
        )
    )
    db.execute(delete(Page).where(Page.upload_id == upload.id))
    db.flush()
    for script_id in script_ids:
        remaining = db.scalar(
            select(func.count()).select_from(Page).where(Page.script_id == script_id)
        )
        script = db.get(Script, script_id)
        if script is not None and not remaining and script.status == ScriptStatus.WAITING:
            db.delete(script)
    db.flush()


def _script_for(db: Session, exam_id: int, student_id: int) -> Script:
    script = db.scalar(
        select(Script).where(Script.exam_id == exam_id, Script.student_id == student_id)
    )
    if script is None:
        script = Script(exam_id=exam_id, student_id=student_id, status=ScriptStatus.WAITING)
        db.add(script)
        db.flush()
    return script


def _next_position(db: Session, script_id: int) -> int:
    current = db.scalar(select(func.max(Page.position)).where(Page.script_id == script_id))
    return (current or 0) + 1


def process_upload(factory: sessionmaker[Session], settings: Settings, upload_id: int) -> None:
    """Render and split one upload. Safe to call again after a crash or restart."""
    with factory() as db:
        upload = db.get(Upload, upload_id)
        if upload is None or upload.status in (UploadStatus.PROCESSED, UploadStatus.FAILED):
            return
        upload.status = UploadStatus.PROCESSING
        db.commit()
        pdf_path = settings.data_dir / upload.stored_path
        exam_id = upload.exam_id

    pages_rel = upload_folder(upload_id) / "pages"
    try:
        result = render_pdf(pdf_path, settings.data_dir / pages_rel, settings)
    except RenderError as exc:
        logger.warning("Upload %s failed: %s", upload_id, exc.code)
        _mark_failed(factory, upload_id, exc.code)
        return

    with factory() as db:
        upload = db.get(Upload, upload_id)
        if upload is None:  # pragma: no cover - deleted meanwhile
            return
        _clear_previous_attempt(db, upload)

        texts = {t for p in result.pages for t in p.qr_texts}
        tokens = {t.split("-")[1] for t in texts if t.count("-") == 2}
        owners = (
            {
                s.token: SheetOwner(s.exam_id, s.student_id)
                for s in db.scalars(select(CoverSheet).where(CoverSheet.token.in_(tokens)))
            }
            if tokens
            else {}
        )
        placements = place_pages(
            result.pages,
            exam_id=exam_id,
            lookup=owners.get,
            students_with_pages=_students_with_pages(db, exam_id, upload_id),
        )

        by_index = {p.index: p for p in result.pages}
        rows: dict[int, Page] = {}
        for placement in placements:
            rendered = by_index[placement.index]
            page = Page(
                upload_id=upload_id,
                source_page_index=placement.index,
                image_path=(pages_rel / rendered.image).as_posix(),
                thumb_path=(pages_rel / rendered.thumb).as_posix(),
                width=rendered.width,
                height=rendered.height,
                rotation_stack=placement.rotation_stack,
                is_cover=placement.is_cover,
                state=PageState.UNASSIGNED,
                unassigned_reason=placement.reason,
                detected_exam_id=placement.detected_exam_id,
            )
            if placement.student_id is not None:
                script = _script_for(db, exam_id, placement.student_id)
                page.state = PageState.ASSIGNED
                page.script_id = script.id
                page.position = _next_position(db, script.id)
            if placement.related_index is not None:
                page.related_page_id = rows[placement.related_index].id
            db.add(page)
            db.flush()
            rows[placement.index] = page

        assigned = sum(1 for p in placements if p.student_id is not None)
        if assigned:
            exam = db.get(Exam, exam_id)
            if exam is not None:
                page_check.clear_check(exam)  # the new pages have not been looked at yet
        upload.page_count = result.page_count
        upload.status = UploadStatus.PROCESSED
        upload.error_code = None
        upload.processed_at = utcnow()
        audit.record(
            db,
            actor=None,
            entity_type="upload",
            entity_id=upload_id,
            action="process",
            new_value={
                "pages": result.page_count,
                "assigned": assigned,
                "unassigned": result.page_count - assigned,
            },
        )
        db.commit()
    logger.info(
        "Upload %s processed: %s pages, %s assigned", upload_id, result.page_count, assigned
    )


def _mark_failed(factory: sessionmaker[Session], upload_id: int, code: str) -> None:
    with factory() as db:
        upload = db.get(Upload, upload_id)
        if upload is None:  # pragma: no cover
            return
        upload.status = UploadStatus.FAILED
        upload.error_code = code
        upload.processed_at = utcnow()
        audit.record(
            db,
            actor=None,
            entity_type="upload",
            entity_id=upload_id,
            action="fail",
            new_value={"error_code": code},
        )
        db.commit()


def retry_upload(db: Session, actor: User, upload_id: int, settings: Settings) -> Upload:
    upload = get_visible_upload(db, actor, upload_id)
    if upload.status != UploadStatus.FAILED:
        raise ConflictError("Only failed uploads can be retried", code="upload.not_failed")
    upload.status = UploadStatus.PENDING
    upload.error_code = None
    jobs.enqueue(
        db,
        JobType.PROCESS_UPLOAD,
        {"upload_id": upload.id},
        f"upload:{upload.id}",
        max_attempts=settings.job_max_attempts,
        requeue=True,
    )
    audit.record(db, actor=actor, entity_type="upload", entity_id=upload.id, action="retry")
    return upload


# --- reading ----------------------------------------------------------------------------------


def get_visible_upload(db: Session, actor: User, upload_id: int) -> Upload:
    upload = db.scalar(
        select(Upload)
        .join(Exam, Upload.exam_id == Exam.id)
        .where(Upload.id == upload_id, Exam.id.in_(visible_exams(actor).with_only_columns(Exam.id)))
    )
    if upload is None:
        raise NotFoundError("Upload")
    return upload


def get_visible_page(db: Session, actor: User, page_id: int) -> Page:
    page = db.scalar(
        select(Page)
        .join(Upload, Page.upload_id == Upload.id)
        .where(
            Page.id == page_id,
            Upload.exam_id.in_(visible_exams(actor).with_only_columns(Exam.id)),
        )
    )
    if page is None:
        raise NotFoundError("Page")
    return page


def list_uploads(db: Session, actor: User, exam_id: int) -> list[Upload]:
    exam = get_visible_exam(db, actor, exam_id)
    return list(
        db.scalars(select(Upload).where(Upload.exam_id == exam.id).order_by(Upload.id.desc()))
    )


def list_scripts(db: Session, actor: User, exam_id: int) -> list[Script]:
    exam = get_visible_exam(db, actor, exam_id)
    return list(
        db.scalars(
            select(Script)
            .join(Student, Script.student_id == Student.id)
            .where(Script.exam_id == exam.id)
            .order_by(Student.code)
        )
    )


def students_without_scripts(db: Session, actor: User, exam_id: int) -> list[Student]:
    exam = get_visible_exam(db, actor, exam_id)
    with_scripts = select(Script.student_id).where(Script.exam_id == exam.id)
    return list(
        db.scalars(
            select(Student)
            .where(Student.class_id == exam.class_id, Student.id.not_in(with_scripts))
            .order_by(Student.code)
        )
    )


def list_tray(db: Session, actor: User, exam_id: int) -> list[Page]:
    exam = get_visible_exam(db, actor, exam_id)
    return list(
        db.scalars(
            select(Page)
            .join(Upload, Page.upload_id == Upload.id)
            .where(
                Upload.exam_id == exam.id,
                Page.state.in_([PageState.UNASSIGNED, PageState.DISCARDED]),
            )
            .order_by(Page.upload_id, Page.source_page_index)
        )
    )


def script_status_counts(db: Session, exam_ids: list[int]) -> dict[int, dict[ScriptStatus, int]]:
    """Per exam, the number of scripts in each status."""
    counts: dict[int, dict[ScriptStatus, int]] = {exam_id: {} for exam_id in exam_ids}
    if not exam_ids:
        return counts
    rows = db.execute(
        select(Script.exam_id, Script.status, func.count())
        .where(Script.exam_id.in_(exam_ids))
        .group_by(Script.exam_id, Script.status)
    )
    for exam_id, status, count in rows:
        counts[exam_id][status] = count
    return counts


def has_uploads(db: Session, exam_id: int) -> bool:
    return db.scalar(select(Upload.id).where(Upload.exam_id == exam_id).limit(1)) is not None


# --- tray actions -----------------------------------------------------------------------------


@dataclass(frozen=True)
class _ExamPages:
    exam: Exam
    pages: list[Page]


def _exam_pages(db: Session, actor: User, exam_id: int, page_ids: list[int]) -> _ExamPages:
    exam = get_visible_exam(db, actor, exam_id)
    pages = list(
        db.scalars(
            select(Page)
            .join(Upload, Page.upload_id == Upload.id)
            .where(Upload.exam_id == exam.id, Page.id.in_(page_ids))
            .order_by(Page.upload_id, Page.source_page_index)
        )
    )
    if len(pages) != len(set(page_ids)):
        raise NotFoundError("Page")
    return _ExamPages(exam, pages)


def _require_editable(script: Script | None) -> None:
    if script is not None and script.status != ScriptStatus.WAITING:
        raise ConflictError(
            "This script is already being marked; its pages cannot change", code="script.locked"
        )


def _compact_positions(db: Session, script: Script) -> None:
    db.flush()
    db.refresh(script)
    for position, page in enumerate(script.pages, start=1):
        page.position = position


def assign_pages(
    db: Session, actor: User, exam_id: int, page_ids: list[int], student_id: int
) -> Script:
    found = _exam_pages(db, actor, exam_id, page_ids)
    student = db.get(Student, student_id)
    if student is None or student.class_id != found.exam.class_id:
        raise NotFoundError("Student")
    if any(p.state == PageState.ASSIGNED for p in found.pages):
        raise ConflictError("Some pages are already in a script", code="page.already_assigned")
    script = _script_for(db, found.exam.id, student.id)
    _require_editable(script)
    position = _next_position(db, script.id)
    for page in found.pages:
        page.state = PageState.ASSIGNED
        page.script_id = script.id
        page.position = position
        page.unassigned_reason = None
        page.related_page_id = None
        position += 1
    page_check.clear_check(found.exam)
    audit.record(
        db,
        actor=actor,
        entity_type="script",
        entity_id=script.id,
        action="assign_pages",
        new_value={"page_ids": [p.id for p in found.pages], "student_code": student.code},
    )
    return script


def unassign_pages(db: Session, actor: User, exam_id: int, page_ids: list[int]) -> None:
    found = _exam_pages(db, actor, exam_id, page_ids)
    scripts: dict[int, Script] = {}
    for page in found.pages:
        if page.script is not None:
            _require_editable(page.script)
            scripts[page.script.id] = page.script
    for page in found.pages:
        old = {"state": page.state.value, "script_id": page.script_id}
        if page.state == PageState.ASSIGNED:
            page.unassigned_reason = UnassignedReason.RETURNED_BY_TEACHER
        # A discarded page keeps its original reason when restored to the tray.
        page.state = PageState.UNASSIGNED
        page.script_id = None
        page.position = None
        audit.record(
            db,
            actor=actor,
            entity_type="page",
            entity_id=page.id,
            action="unassign",
            old_value=old,
            new_value={"state": "unassigned"},
        )
    for script in scripts.values():
        _compact_positions(db, script)
        if not script.pages:
            db.delete(script)


def discard_pages(db: Session, actor: User, exam_id: int, page_ids: list[int]) -> None:
    found = _exam_pages(db, actor, exam_id, page_ids)
    if any(p.state == PageState.ASSIGNED for p in found.pages):
        raise ConflictError(
            "Return pages to the tray before discarding", code="page.already_assigned"
        )
    for page in found.pages:
        page.state = PageState.DISCARDED
        audit.record(
            db,
            actor=actor,
            entity_type="page",
            entity_id=page.id,
            action="discard",
        )
