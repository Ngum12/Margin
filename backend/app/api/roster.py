from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.db.models import Job, JobType, RosterImport
from app.errors import PayloadTooLargeError, ValidationFailedError
from app.schemas.classes import StudentOut
from app.schemas.common import ApiModel, ShortText
from app.schemas.roster import ActiveIn, RegisterUpdate, RosterRows
from app.services import audit, jobs, roster, school_results
from app.services.access import get_visible_class, get_visible_exam, get_visible_student

router = APIRouter(tags=["registers and history"])


def output(db: DbSession, item: RosterImport) -> dict[str, Any]:
    job = db.scalar(select(Job).where(Job.idempotency_key == f"roster:{item.id}"))
    return {
        "id": item.id,
        "status": job.status.value if job and item.status == "queued" else item.status,
        "error": item.error,
        "rows": item.rows,
        "model_name": item.model_name,
        "model_version": item.model_version,
        "prompt_version": item.prompt_version,
    }


@router.get("/classes/{class_id}/imports")
def imports(class_id: int, db: DbSession, actor: CurrentUser) -> list[dict[str, Any]]:
    get_visible_class(db, actor, class_id)
    return [
        output(db, item)
        for item in db.scalars(
            select(RosterImport)
            .where(RosterImport.class_id == class_id)
            .order_by(RosterImport.id.desc())
        )
    ]


@router.post("/classes/{class_id}/imports", status_code=202)
async def receive(
    class_id: int,
    suffix: str,
    request: Request,
    db: DbSession,
    actor: CurrentUser,
    settings: AppSettings,
) -> dict[str, Any]:
    get_visible_class(db, actor, class_id)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > roster.MAX_BYTES:
            raise PayloadTooLargeError("Register too large")
    return output(db, roster.receive(db, actor, class_id, bytes(body), suffix, settings))


@router.post("/roster-imports/{ident}/confirm")
def confirm(ident: int, data: RosterRows, db: DbSession, actor: CurrentUser) -> list[StudentOut]:
    return [StudentOut.model_validate(s) for s in roster.confirm(db, actor, ident, data)]


@router.post("/roster-imports/{ident}/retry")
def retry(ident: int, db: DbSession, actor: CurrentUser) -> dict[str, Any]:
    item = roster.visible(db, actor, ident)
    if item.status == "confirmed":
        raise ValidationFailedError("Already confirmed")
    jobs.enqueue(
        db,
        JobType.EXTRACT_ROSTER,
        {"roster_id": item.id},
        f"roster:{item.id}",
        max_attempts=3,
        requeue=True,
    )
    item.status = "queued"
    return output(db, item)


@router.get("/roster-imports/{ident}/original")
def original(ident: int, db: DbSession, actor: CurrentUser, settings: AppSettings) -> FileResponse:
    item = roster.visible(db, actor, ident)
    return FileResponse(
        settings.data_dir / item.file_path,
        filename=f"register{item.suffix}",
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


@router.put("/classes/{class_id}/register-order", status_code=204)
def order(class_id: int, data: RegisterUpdate, db: DbSession, actor: CurrentUser) -> None:
    get_visible_class(db, actor, class_id)
    rows = roster.class_students(db, class_id)
    if set(data.student_ids) != {s.id for s in rows} or len(set(data.student_ids)) != len(
        data.student_ids
    ):
        raise ValidationFailedError("Include every active student once", code="roster.order")
    positions = {ident: index for index, ident in enumerate(data.student_ids, 1)}
    for student in rows:
        student.register_position = positions[student.id]
    audit.record(
        db,
        actor=actor,
        entity_type="school_class",
        entity_id=class_id,
        action="register_order",
        new_value={"student_ids": data.student_ids},
    )


@router.put("/students/{student_id}/active")
def active(student_id: int, data: ActiveIn, db: DbSession, actor: CurrentUser) -> StudentOut:
    student = get_visible_student(db, actor, student_id)
    before = student.is_active
    student.is_active = data.active
    audit.record(
        db,
        actor=actor,
        entity_type="student",
        entity_id=student.id,
        action="student_active",
        old_value={"active": before},
        new_value={"active": data.active},
    )
    return StudentOut.model_validate(student)


@router.get("/students/{student_id}/history")
def history(student_id: int, db: DbSession, actor: CurrentUser) -> list[dict[str, Any]]:
    return school_results.history(db, actor, student_id)


@router.get("/exams/{exam_id}/results.xlsx")
def spreadsheet(exam_id: int, db: DbSession, actor: CurrentUser) -> Response:
    return Response(
        school_results.excel(db, actor, exam_id),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="results-{exam_id}.xlsx"',
            "Cache-Control": "no-store",
        },
    )


class TermIn(ApiModel):
    term: ShortText


@router.get("/exams/{exam_id}/term")
def get_term(exam_id: int, db: DbSession, actor: CurrentUser) -> dict[str, str]:
    exam = get_visible_exam(db, actor, exam_id)
    return {"term": exam.term, "academic_year": exam.school_class.academic_year}


@router.put("/exams/{exam_id}/term", status_code=204)
def term(exam_id: int, data: TermIn, db: DbSession, actor: CurrentUser) -> None:
    exam = get_visible_exam(db, actor, exam_id)
    old = exam.term
    exam.term = data.term
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="term",
        old_value={"term": old},
        new_value={"term": exam.term},
    )
