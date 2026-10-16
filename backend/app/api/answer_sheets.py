from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.db.models import AnswerSheet, PrintJob
from app.errors import NotFoundError
from app.services import answer_sheets, cover_sheets, printing
from app.services.access import get_visible_exam

router = APIRouter(tags=["answer sheets"])


class PrepareIn(BaseModel):
    pages_per_student: int = Field(default=2, ge=1, le=20)
    spares: int = Field(default=0, ge=0, le=40)
    layout: Literal["answer", "labels", "cover"] = "answer"
    send_to_printer: bool = False
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")


@router.get("/exams/{exam_id}/answer-sheets")
def list_sheets(exam_id: int, db: DbSession, actor: CurrentUser) -> dict[str, object]:
    exam = get_visible_exam(db, actor, exam_id)
    rows = list(
        db.scalars(
            select(AnswerSheet).where(AnswerSheet.exam_id == exam.id, AnswerSheet.active.is_(True))
        )
    )
    return {
        "pages_per_student": max((s.page_number for s in rows if not s.spare), default=2),
        "issued": len(rows),
        "unassigned_spares": sum(1 for s in rows if s.spare and s.student_id is None),
    }


@router.post("/exams/{exam_id}/answer-sheets", status_code=201)
def prepare(
    exam_id: int, body: PrepareIn, db: DbSession, actor: CurrentUser, settings: AppSettings
) -> dict[str, object]:
    exam = get_visible_exam(db, actor, exam_id)
    job = db.scalar(
        select(PrintJob).where(PrintJob.request_key == f"{actor.id}:{body.request_key}")
    )
    if job is None:
        if body.layout == "cover":
            cover_sheets.prepare_sheets(db, actor, exam.id)
            _, content = cover_sheets.cover_sheets_pdf(db, actor, exam.id)
        else:
            sheets = answer_sheets.prepare(
                db, actor, exam.id, body.pages_per_student, body.spares, body.layout
            )
            content = answer_sheets.document(db, exam, sheets, body.layout)
        job = answer_sheets.queue_document(
            db, actor, exam, content, body.request_key, settings, body.send_to_printer
        )
    if job.exam_id != exam.id:
        raise NotFoundError("Document")
    return {
        "id": job.id,
        "status": job.status,
        "download_url": f"/api/print-jobs/{job.id}/sheets.pdf",
    }


@router.get("/print-jobs/{job_id}/sheets.pdf")
def download(job_id: int, db: DbSession, actor: CurrentUser, settings: AppSettings) -> FileResponse:
    job = next((j for j in printing.visible_jobs(db, actor) if j.id == job_id), None)
    if not job or job.kind != "answer_sheets" or not job.file_path:
        raise NotFoundError("Document")
    return FileResponse(
        settings.data_dir / job.file_path,
        media_type="application/pdf",
        filename="margin-answer-sheets.pdf",
        headers={"Cache-Control": "no-store"},
    )
