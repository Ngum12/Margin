"""Stable-file intake and school-scoped QR routing, independent of the HTTP upload flow."""

import hashlib
import os
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.clock import utcnow
from app.config import Settings
from app.db.models import (
    AnswerSheet,
    CoverSheet,
    Exam,
    ExamAbsence,
    ExamStatus,
    Hardware,
    IntakePage,
    Job,
    JobStatus,
    JobType,
    Page,
    PageState,
    ScanBatch,
    SchoolClass,
    Script,
    ScriptStatus,
    Student,
    Upload,
    UploadStatus,
    User,
)
from app.errors import ConflictError, NotFoundError
from app.pdf.runner import RenderError, render_pdf
from app.services import audit, jobs, page_check, uploads
from app.services.access import get_visible_exam
from app.services.roster import eligible_student
from app.sheets.tokens import parse_payload

EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def inbox_path(settings: Settings, school_id: int) -> Path:
    return settings.data_dir / "scan-inbox" / str(school_id)


def hardware(db: Session, school_id: int) -> Hardware:
    row = db.scalar(select(Hardware).where(Hardware.school_id == school_id))
    if row is None:
        row = Hardware(school_id=school_id)
        db.add(row)
        db.flush()
    return row


def receive(db: Session, school_id: int, source: Path, settings: Settings) -> ScanBatch | None:
    """Copy first; verify the source did not change; commit before the caller removes it."""
    before = source.stat()
    if source.is_symlink() or not source.is_file():
        return None
    if before.st_size > settings.max_upload_mb * 1024 * 1024:
        # Leave oversized files in place, visible in hardware status; do not copy unbounded data.
        return None
    root = settings.data_dir / "scan-archive" / str(school_id)
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / (hashlib.sha256(source.name.encode()).hexdigest() + ".part")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as inp, temporary.open("wb") as out:
            total = 0
            while chunk := inp.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_mb * 1024 * 1024:
                    return None
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return None
        sha = digest.hexdigest()
        existing = db.scalar(
            select(ScanBatch).where(ScanBatch.school_id == school_id, ScanBatch.sha256 == sha)
        )
        if existing:
            return existing
        relative = Path("scan-archive") / str(school_id) / (sha + source.suffix.lower())
        temporary.replace(settings.data_dir / relative)
        batch = ScanBatch(
            school_id=school_id,
            sha256=sha,
            source_name=source.name[:255],
            size_bytes=before.st_size,
            stored_path=relative.as_posix(),
        )
        if db.scalar(
            select(Upload.id)
            .join(Exam)
            .join(SchoolClass)
            .where(Upload.sha256 == sha, SchoolClass.school_id == school_id)
            .limit(1)
        ):
            batch.status = "duplicate"
        db.add(batch)
        db.flush()
        hardware(db, school_id).last_scan_at = utcnow()
        audit.record(
            db,
            actor=None,
            entity_type="scan_batch",
            entity_id=batch.id,
            action="import",
            new_value={"sha256": sha},
        )
        return batch
    finally:
        temporary.unlink(missing_ok=True)


def attach(
    db: Session,
    batch: ScanBatch,
    item: IntakePage,
    exam: Exam,
    student: Student,
    *,
    is_cover: bool = False,
) -> Page:
    if exam.status == ExamStatus.DRAFT:
        raise ConflictError("Exam not ready", code="exam.sheets_need_ready")
    if db.scalar(
        select(ExamAbsence.id).where(
            ExamAbsence.exam_id == exam.id, ExamAbsence.student_id == student.id
        )
    ):
        raise ConflictError("Student marked absent", code="hardware.absent_has_scan")
    sheet = db.get(AnswerSheet, item.answer_sheet_id) if item.answer_sheet_id else None
    if sheet and db.scalar(
        select(Page.id)
        .join(Script, Page.script_id == Script.id)
        .where(
            Script.exam_id == exam.id,
            Script.student_id == student.id,
            Page.position == sheet.page_number,
            Page.state == PageState.ASSIGNED,
        )
    ):
        raise ConflictError("Page already received", code="sheets.duplicate_page")
    script = uploads._script_for(db, exam.id, student.id)
    if not uploads.pages_mutable(db, script):
        raise ConflictError("Script pages are locked", code="script.locked")
    upload = db.scalar(
        select(Upload).where(Upload.exam_id == exam.id, Upload.sha256 == batch.sha256)
    )
    if upload is None:
        upload = Upload(
            exam_id=exam.id,
            uploaded_by_id=None,
            original_filename=batch.source_name,
            stored_path=batch.stored_path,
            sha256=batch.sha256,
            size_bytes=batch.size_bytes or 0,
            status=UploadStatus.PROCESSED,
            processed_at=utcnow(),
        )
        db.add(upload)
        db.flush()
    page = Page(
        upload_id=upload.id,
        answer_sheet_id=item.answer_sheet_id,
        source_page_index=item.source_index,
        image_path=item.image_path,
        thumb_path=item.thumb_path,
        width=item.width,
        height=item.height,
        rotation_stack=item.rotation,
        is_cover=is_cover,
        state=PageState.ASSIGNED,
        script_id=script.id,
        position=sheet.page_number if sheet else uploads._next_position(db, script.id),
    )
    db.add(page)
    db.flush()
    item.page_id, item.exam_id, item.reason = page.id, exam.id, None
    upload.page_count = (upload.page_count or 0) + 1
    page_check.clear_check(exam)
    return page


def process(factory: sessionmaker[Session], settings: Settings, batch_id: int) -> None:
    with factory() as db:
        batch = db.get(ScanBatch, batch_id)
        if batch is None or batch.status != "pending":
            return
        source = settings.data_dir / (batch.prepared_path or batch.stored_path)
    relative = Path("scan-pages") / str(batch_id)
    try:
        rendered = render_pdf(source, settings.data_dir / relative, settings)
    except RenderError as exc:
        with factory() as db:
            batch = db.get(ScanBatch, batch_id)
            if batch:
                batch.status, batch.error_code = "quarantine", exc.code
                db.commit()
        return
    with factory() as db:
        batch = db.get(ScanBatch, batch_id)
        if batch is None or batch.status != "pending":
            return
        owners = {
            s.token: s
            for s in db.scalars(
                select(CoverSheet)
                .join(Exam)
                .join(SchoolClass)
                .where(SchoolClass.school_id == batch.school_id)
            )
        }
        page_owners = {
            s.token: s
            for s in db.scalars(
                select(AnswerSheet)
                .join(Exam)
                .join(SchoolClass)
                .where(SchoolClass.school_id == batch.school_id)
            )
        }
        current: CoverSheet | None = None
        rotation = 0
        for image in rendered.pages:
            token = parse_payload(image.qr_texts[0]).token if len(image.qr_texts) == 1 else None
            sheet = page_owners.get(token or "")
            if sheet is not None:
                current = None
                rotation = 0
                item = IntakePage(
                    batch_id=batch.id,
                    source_index=image.index,
                    answer_sheet_id=sheet.id,
                    image_path=(relative / image.image).as_posix(),
                    thumb_path=(relative / image.thumb).as_posix(),
                    width=image.width,
                    height=image.height,
                    rotation=image.qr_rotation,
                    exam_id=sheet.exam_id,
                    reason="spare" if sheet.student_id is None else "retired_sheet",
                )
                db.add(item)
                db.flush()
                exam = db.get(Exam, sheet.exam_id)
                student = db.get(Student, sheet.student_id) if sheet.student_id else None
                if sheet.spare and sheet.student_id is None:
                    jobs.enqueue(
                        db,
                        JobType.IDENTIFY_SPARE,
                        {"intake_page_id": item.id},
                        f"identify-spare:{item.id}",
                        max_attempts=settings.job_max_attempts,
                    )
                if sheet.active and exam and student:
                    try:
                        attach(db, batch, item, exam, student)
                    except ConflictError as exc:
                        item.reason = {
                            "sheets.duplicate_page": "duplicate_page",
                            "hardware.absent_has_scan": "absent",
                            "exam.sheets_need_ready": "exam_not_ready",
                        }.get(exc.code, "script_locked")
                continue
            owner = owners.get(token or "")
            is_cover = owner is not None
            reason: str | None = None
            if image.qr_texts or image.cover_frame or image.qr_damaged:
                current = owner
                rotation = image.qr_rotation
                if owner:
                    existing = db.scalar(
                        select(Script.id)
                        .join(Page)
                        .where(
                            Script.exam_id == owner.exam_id, Script.student_id == owner.student_id
                        )
                    )
                    if existing:
                        current, reason = None, "already_uploaded"
                else:
                    reason = "qr_unreadable"
            item = IntakePage(
                batch_id=batch.id,
                source_index=image.index,
                image_path=(relative / image.image).as_posix(),
                thumb_path=(relative / image.thumb).as_posix(),
                width=image.width,
                height=image.height,
                rotation=rotation,
                exam_id=owner.exam_id if owner else (current.exam_id if current else None),
                reason=reason or "qr_unreadable",
            )
            db.add(item)
            db.flush()
            if current:
                exam, student = db.get(Exam, current.exam_id), db.get(Student, current.student_id)
                if exam and student and exam.status != ExamStatus.DRAFT:
                    try:
                        attach(db, batch, item, exam, student, is_cover=is_cover)
                    except ConflictError as exc:
                        item.reason = (
                            "absent" if exc.code == "hardware.absent_has_scan" else "script_locked"
                        )
                else:
                    item.reason = "exam_not_ready"
        batch.status = "processed"
        audit.record(
            db,
            actor=None,
            entity_type="scan_batch",
            entity_id=batch.id,
            action="route",
            new_value={"pages": len(rendered.pages)},
        )
        db.commit()


def assign(
    db: Session,
    actor: User,
    item_id: int,
    exam_id: int,
    student_id: int,
    page_number: int | None = None,
    *,
    re_mark: bool = False,
    settings: Settings | None = None,
) -> None:
    exam = get_visible_exam(db, actor, exam_id)
    item = db.get(IntakePage, item_id)
    batch = db.get(ScanBatch, item.batch_id) if item else None
    student = db.get(Student, student_id)
    if (
        not item
        or not batch
        or batch.school_id != actor.school_id
        or not student
        or not eligible_student(exam, student)
        or (
            not actor.is_admin
            and item.exam_id != exam.id
            and not (item.exam_id is None and batch.captured_by_id == actor.id)
        )
    ):
        raise NotFoundError("Page")
    if item.page_id or item.discarded or exam.status == ExamStatus.DRAFT:
        raise ConflictError("Page cannot be assigned", code="page.already_assigned")
    sheet = db.get(AnswerSheet, item.answer_sheet_id) if item.answer_sheet_id else None
    if sheet is None and page_number is not None:
        sheet = db.scalar(
            select(AnswerSheet)
            .where(
                AnswerSheet.exam_id == exam.id,
                AnswerSheet.student_id == student.id,
                AnswerSheet.active.is_(True),
                AnswerSheet.page_number == page_number,
            )
            .order_by(AnswerSheet.id)
            .limit(1)
        )
        if sheet is not None:
            item.answer_sheet_id = sheet.id
    if sheet:
        if sheet.exam_id != exam.id or (not sheet.spare and sheet.student_id != student.id):
            raise ConflictError(
                "QR belongs to another student or exam", code="sheets.wrong_student"
            )
        if sheet.spare:
            sheet.student_id = student.id
            sheet.page_number = page_number or 1
            sheet.active = True
    script = uploads._script_for(db, exam.id, student.id)
    restarting = re_mark and script.status != ScriptStatus.WAITING
    if restarting:
        active = db.scalar(
            select(Job.id)
            .where(
                Job.idempotency_key.in_([f"transcribe:{script.id}", f"mark:{script.id}"]),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
            .limit(1)
        )
        if script.status == ScriptStatus.CONFIRMED or active or settings is None:
            raise ConflictError(
                "Reopen a confirmed script; wait for running work", code="script.locked"
            )
        old = {"ai_run": script.ai_run, "status": script.status.value}
        script.ai_run += 1
        script.status = ScriptStatus.WAITING
        script.manual_reason = None
        script.ai_started_at = None
        audit.record(
            db,
            actor=actor,
            entity_type="script",
            entity_id=script.id,
            action="add_page_and_remark",
            old_value=old,
            new_value={"ai_run": script.ai_run},
        )
    attach(db, batch, item, exam, student)
    if restarting and settings is not None:
        jobs.enqueue(
            db,
            JobType.TRANSCRIBE_SCRIPT,
            {"script_id": script.id},
            f"transcribe:{script.id}",
            max_attempts=settings.job_max_attempts,
            requeue=True,
        )
        exam.status = ExamStatus.MARKING
    audit.record(
        db,
        actor=actor,
        entity_type="intake_page",
        entity_id=item.id,
        action="assign",
        new_value={"exam_id": exam.id, "student_id": student.id},
    )


class InboxPoller:
    """One poller per worker. A restart deliberately repeats the stability observation."""

    def __init__(self, stable_seconds: float = 5) -> None:
        self.stable_seconds = stable_seconds
        self.seen: dict[Path, tuple[int, int, float]] = {}

    def tick(self, factory: sessionmaker[Session], settings: Settings) -> None:
        from app.services.capture import prepare

        prepare(factory, settings)
        with factory() as db:
            schools = list(
                db.scalars(select(Hardware.school_id).where(Hardware.inbox_enabled.is_(True)))
            )
        now = time.monotonic()
        present: set[Path] = set()
        for school_id in schools:
            folder = inbox_path(settings, school_id)
            folder.mkdir(parents=True, exist_ok=True)
            for source in folder.iterdir():
                if (
                    source.suffix.lower() not in EXTENSIONS
                    or source.is_symlink()
                    or not source.is_file()
                ):
                    continue
                present.add(source)
                try:
                    stat = source.stat()
                    prior = self.seen.get(source)
                    if not prior or prior[:2] != (stat.st_size, stat.st_mtime_ns):
                        self.seen[source] = stat.st_size, stat.st_mtime_ns, now
                        continue
                    if now - prior[2] < self.stable_seconds:
                        continue
                    with factory() as db:
                        batch = receive(db, school_id, source, settings)
                        db.commit()
                        if batch:
                            # Do not remove a file the copier changed after our verified copy.
                            final = source.stat()
                            if (final.st_size, final.st_mtime_ns) == prior[:2]:
                                source.unlink()
                except OSError:
                    # Copier locks and transient sharing failures are retried next poll.
                    continue
        self.seen = {p: v for p, v in self.seen.items() if p in present}
        with factory() as db:
            pending = db.scalar(
                select(ScanBatch.id)
                .where(ScanBatch.status == "pending")
                .order_by(ScanBatch.id)
                .limit(1)
            )
        if pending is not None:
            process(factory, settings, pending)
