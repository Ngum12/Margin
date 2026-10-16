from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api.deps import AdminUser, AppSettings, CurrentUser, DbSession
from app.clock import utcnow
from app.db.models import Exam, IntakePage, Page, PageState, ScanBatch, Script, ScriptStatus
from app.errors import ConflictError, NotFoundError, ValidationFailedError
from app.services import audit, ipp, printing, scan_inbox, uploads
from app.services.access import get_visible_script, visible_exams
from app.services.exports import require_confirmed
from app.services.results import script_results

router = APIRouter(tags=["hardware"])


class AttendanceIn(BaseModel):
    absent: bool


@router.get("/exams/{exam_id}/attendance")
def attendance(exam_id: int, db: DbSession, actor: CurrentUser) -> list[dict[str, object]]:
    from app.db.models import ExamAbsence, Student
    from app.services.access import get_visible_exam
    from app.services.answer_sheets import readiness

    exam = get_visible_exam(db, actor, exam_id)
    absences = set(db.scalars(select(ExamAbsence.student_id).where(ExamAbsence.exam_id == exam.id)))
    received = set(db.scalars(select(Script.student_id).where(Script.exam_id == exam.id)))
    return [
        {
            "id": student.id,
            "name": student.display_name or student.code,
            "absent": student.id in absences,
            "received": student.id in received,
            "missing_pages": readiness(db, exam.id, student.id)[0]
            if student.id in received
            else [],
        }
        for student in db.scalars(
            select(Student).where(Student.class_id == exam.class_id).order_by(Student.id)
        )
    ]


@router.put("/exams/{exam_id}/attendance/{student_id}", status_code=204)
def set_attendance(
    exam_id: int, student_id: int, body: AttendanceIn, db: DbSession, actor: CurrentUser
) -> Response:
    from app.db.models import ExamAbsence, Student
    from app.services.access import get_visible_exam

    exam = get_visible_exam(db, actor, exam_id)
    student = db.get(Student, student_id)
    if not student or student.class_id != exam.class_id:
        raise NotFoundError("Student")
    if body.absent and db.scalar(
        select(Script.id).where(Script.exam_id == exam.id, Script.student_id == student.id)
    ):
        raise ConflictError(
            "Received script cannot be marked absent", code="hardware.absent_has_scan"
        )
    row = db.scalar(
        select(ExamAbsence).where(
            ExamAbsence.exam_id == exam.id, ExamAbsence.student_id == student.id
        )
    )
    if body.absent and row is None:
        db.add(ExamAbsence(exam_id=exam.id, student_id=student.id, recorded_by_id=actor.id))
    elif not body.absent and row:
        db.delete(row)
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="attendance",
        new_value={"student_id": student.id, "absent": body.absent},
    )
    return Response(status_code=204)


class HardwareIn(BaseModel):
    inbox_enabled: bool
    printer_uri: str = Field(max_length=500)
    duplex: bool = True


class PrintIn(BaseModel):
    exam_id: int | None = None
    script_ids: list[int] | None = Field(default=None, max_length=1000)
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")
    kind: Literal["feedback", "full", "test"] = "feedback"
    unprinted: bool = False


class AssignIn(BaseModel):
    exam_id: int
    student_id: int
    page_number: int | None = Field(default=None, ge=1, le=1000)
    re_mark: bool = False


class RetryIn(BaseModel):
    acknowledge_uncertain: bool = False


@router.get("/hardware")
def settings_get(db: DbSession, actor: AdminUser, settings: AppSettings) -> dict[str, object]:
    row = scan_inbox.hardware(db, actor.school_id)
    folder = scan_inbox.inbox_path(settings, actor.school_id)
    folder.mkdir(parents=True, exist_ok=True)
    return {
        "inbox_enabled": row.inbox_enabled,
        "inbox_path": str(folder.resolve()),
        "printer_uri": row.printer_uri,
        "duplex": row.duplex,
        "last_scan_at": row.last_scan_at,
        "test_started_at": row.test_started_at,
        "test_received": bool(
            row.test_started_at and row.last_scan_at and row.last_scan_at >= row.test_started_at
        ),
        "waiting_files": sum(1 for p in folder.iterdir() if p.is_file()),
        "oversized_files": sum(
            1
            for p in folder.iterdir()
            if p.is_file() and p.stat().st_size > settings.max_upload_mb * 1024 * 1024
        ),
    }


@router.put("/hardware")
def settings_put(
    body: HardwareIn, db: DbSession, actor: AdminUser, settings: AppSettings
) -> dict[str, object]:
    if body.printer_uri:
        try:
            ipp.validate_uri(body.printer_uri)
        except ipp.PrinterError as exc:
            raise ValidationFailedError("Use a private IPP printer address", code=str(exc)) from exc
    row = scan_inbox.hardware(db, actor.school_id)
    row.inbox_enabled, row.printer_uri, row.duplex = (
        body.inbox_enabled,
        body.printer_uri,
        body.duplex,
    )
    audit.record(db, actor=actor, entity_type="hardware", entity_id=row.id, action="configure")
    return settings_get(db, actor, settings)


@router.post("/hardware/test-scan")
def test_scan(db: DbSession, actor: AdminUser) -> dict[str, object]:
    row = scan_inbox.hardware(db, actor.school_id)
    row.test_started_at = utcnow()
    return {"started_at": row.test_started_at}


@router.post("/hardware/test-printer")
def test_printer(db: DbSession, actor: AdminUser) -> dict[str, object]:
    try:
        ipp.capabilities(scan_inbox.hardware(db, actor.school_id).printer_uri)
        return {"connected": True}
    except ipp.PrinterError as exc:
        return {"connected": False, "error_code": str(exc)}


@router.get("/intake")
def intake(db: DbSession, actor: CurrentUser) -> dict[str, object]:
    query = (
        select(IntakePage)
        .join(ScanBatch)
        .where(
            ScanBatch.school_id == actor.school_id,
            IntakePage.page_id.is_(None),
            IntakePage.discarded.is_(False),
        )
    )
    if not actor.is_admin:
        query = query.where(
            or_(
                IntakePage.exam_id.in_(visible_exams(actor).with_only_columns(Exam.id)),
                (IntakePage.exam_id.is_(None)) & (ScanBatch.captured_by_id == actor.id),
            )
        )
    pages = list(db.scalars(query.order_by(IntakePage.id).limit(200)))
    quarantine = (
        list(
            db.scalars(
                select(ScanBatch)
                .where(ScanBatch.school_id == actor.school_id, ScanBatch.status == "quarantine")
                .limit(100)
            )
        )
        if actor.is_admin
        else []
    )
    return {
        "pages": [
            {
                "id": p.id,
                "batch_id": p.batch_id,
                "page": p.source_index + 1,
                "reason": p.reason,
                "exam_id": p.exam_id,
                "suggested_student_id": p.suggested_student_id,
                "answer_sheet_id": p.answer_sheet_id,
            }
            for p in pages
        ],
        "quarantine": [{"id": b.id, "error_code": b.error_code} for b in quarantine],
        "batches": [
            {"id": b.id, "status": b.status}
            for b in db.scalars(
                select(ScanBatch)
                .where(ScanBatch.school_id == actor.school_id, ScanBatch.status != "removed")
                .order_by(ScanBatch.id.desc())
                .limit(20)
            )
        ]
        if actor.is_admin
        else [],
    }


@router.get("/intake/{item_id}/image")
def intake_image(
    item_id: int, db: DbSession, actor: CurrentUser, settings: AppSettings
) -> FileResponse:
    item = db.get(IntakePage, item_id)
    batch = db.get(ScanBatch, item.batch_id) if item else None
    if not item or not batch or batch.school_id != actor.school_id:
        raise NotFoundError("Page")
    if (
        not actor.is_admin
        and not (item.exam_id is None and batch.captured_by_id == actor.id)
        and db.scalar(visible_exams(actor).where(Exam.id == item.exam_id)) is None
    ):
        raise NotFoundError("Page")
    return FileResponse(
        settings.data_dir / item.image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/intake/{item_id}/assign", status_code=204)
def assign_page(
    item_id: int, body: AssignIn, db: DbSession, actor: CurrentUser, settings: AppSettings
) -> Response:
    scan_inbox.assign(
        db,
        actor,
        item_id,
        body.exam_id,
        body.student_id,
        body.page_number,
        re_mark=body.re_mark,
        settings=settings,
    )
    return Response(status_code=204)


@router.post("/intake/{item_id}/discard", status_code=204)
def discard_page(item_id: int, db: DbSession, actor: CurrentUser) -> Response:
    item = db.get(IntakePage, item_id)
    batch = db.get(ScanBatch, item.batch_id) if item else None
    if not item or not batch or batch.school_id != actor.school_id or item.page_id:
        raise NotFoundError("Page")
    if (
        not actor.is_admin
        and not (item.exam_id is None and batch.captured_by_id == actor.id)
        and db.scalar(visible_exams(actor).where(Exam.id == item.exam_id)) is None
    ):
        raise NotFoundError("Page")
    item.discarded = True
    audit.record(db, actor=actor, entity_type="intake_page", entity_id=item.id, action="discard")
    return Response(status_code=204)


@router.get("/print-jobs")
def print_jobs(db: DbSession, actor: CurrentUser) -> list[dict[str, object]]:
    return [
        {
            "id": j.id,
            "exam_id": j.exam_id,
            "script_ids": j.script_ids,
            "status": j.status,
            "error_code": j.error_code,
            "kind": j.kind,
            "created_at": j.created_at,
        }
        for j in printing.visible_jobs(db, actor)
    ]


@router.post("/print-jobs", status_code=201)
def print_request(body: PrintIn, db: DbSession, actor: CurrentUser) -> dict[str, object]:
    job = printing.request_print(
        db, actor, body.exam_id, body.script_ids, body.request_key, body.kind, body.unprinted
    )
    return {"id": job.id, "status": job.status}


@router.post("/print-jobs/{job_id}/retry")
def print_retry(job_id: int, body: RetryIn, db: DbSession, actor: CurrentUser) -> dict[str, object]:
    job = printing.retry(db, actor, job_id, body.acknowledge_uncertain)
    return {"id": job.id, "status": job.status}


@router.get("/scripts/{script_id}/feedback.pdf")
def feedback_download(script_id: int, db: DbSession, actor: CurrentUser) -> Response:
    script = get_visible_script(db, actor, script_id)
    require_confirmed(script)
    exam = db.get(Exam, script.exam_id)
    if exam is None:
        raise NotFoundError("Exam")
    content = printing.feedback_pdf(
        db,
        script_results(db, exam, [script], with_pages=True),
        exam.title,
        actor.preferred_language.value,
    )
    audit.record(
        db, actor=actor, entity_type="script", entity_id=script.id, action="download_feedback"
    )
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="feedback-{script.id}.pdf"',
        },
    )


@router.delete("/scan-batches/{batch_id}", status_code=204)
def remove_batch(batch_id: int, db: DbSession, actor: AdminUser) -> Response:
    batch = db.get(ScanBatch, batch_id)
    if not batch or batch.school_id != actor.school_id:
        raise NotFoundError("Scan batch")
    pages = list(
        db.scalars(
            select(Page)
            .join(IntakePage, IntakePage.page_id == Page.id)
            .where(IntakePage.batch_id == batch.id)
        )
    )
    scripts = list(
        db.scalars(select(Script).where(Script.id.in_([p.script_id for p in pages if p.script_id])))
    )
    if any(s.status != ScriptStatus.WAITING for s in scripts):
        raise ConflictError("Confirmed or marking scripts cannot be removed", code="script.locked")
    for exam_id in {p.upload.exam_id for p in pages}:
        uploads.unassign_pages(
            db, actor, exam_id, [p.id for p in pages if p.upload.exam_id == exam_id]
        )
    for page in pages:
        page.state = PageState.DISCARDED
    for item in db.scalars(select(IntakePage).where(IntakePage.batch_id == batch.id)):
        item.discarded = True
    batch.status = "removed"
    audit.record(db, actor=actor, entity_type="scan_batch", entity_id=batch.id, action="remove")
    # Preserve the original and audit evidence, but remove the batch from active work.
    return Response(status_code=204)
