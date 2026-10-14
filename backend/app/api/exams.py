from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbSession
from app.db.models import Exam
from app.errors import Issue, ValidationFailedError
from app.marks import from_half_marks
from app.schemas.common import IssueOut
from app.schemas.exams import (
    ExamCreateIn,
    ExamDetailOut,
    ExamStatusIn,
    ExamSummaryOut,
    ExamUpdateIn,
    ImportPreviewOut,
    PointOut,
    QuestionOut,
    ScriptCounts,
    SubjectOut,
    ValidationReportOut,
)
from app.schemas.mark_scheme import MarkSchemeIn
from app.services import exams as exam_service
from app.services.mark_scheme import MarkSchemeReport, validate_mark_scheme
from app.services.mark_scheme_import import MAX_CSV_BYTES, decode_csv, parse_mark_scheme_csv
from app.subjects.registry import get_registry

router = APIRouter(tags=["exams"])


def _report_out(report: MarkSchemeReport) -> ValidationReportOut:
    return ValidationReportOut(
        blocking=[IssueOut.of(i) for i in report.blocking],
        readiness=[IssueOut.of(i) for i in report.readiness],
        notices=[IssueOut.of(i) for i in report.notices],
        is_ready=report.is_ready,
    )


def _summary_out(exam: Exam) -> ExamSummaryOut:
    return ExamSummaryOut(
        id=exam.id,
        class_id=exam.class_id,
        class_name=exam.school_class.name,
        subject_code=exam.subject_code,
        title=exam.title,
        exam_date=exam.exam_date,
        status=exam.status,
        question_count=len(exam.questions),
        total_marks=from_half_marks(exam_service.total_half_marks(exam)),
        # Scripts arrive in Phase 2; counts are zero until then.
        scripts=ScriptCounts(),
        updated_at=exam.updated_at,
    )


def _detail_out(exam: Exam) -> ExamDetailOut:
    return ExamDetailOut(
        **_summary_out(exam).model_dump(),
        questions=[
            QuestionOut(
                id=q.id,
                label=q.label,
                prompt_text=q.prompt_text,
                max_marks=from_half_marks(q.max_half_marks),
                points=[
                    PointOut(
                        id=p.id,
                        description=p.description,
                        marks=from_half_marks(p.half_marks),
                        alternatives=list(p.alternatives),
                    )
                    for p in q.points
                ],
            )
            for q in exam.questions
        ],
        validation=_report_out(exam_service.validation_of(exam)),
    )


@router.get("/subjects")
def list_subjects(user: CurrentUser) -> list[SubjectOut]:
    return [
        SubjectOut(code=s.code, name_en=s.names.en, name_fr=s.names.fr)
        for s in get_registry().for_curriculum(user.school.curriculum)
    ]


@router.get("/exams")
def list_exams(db: DbSession, user: CurrentUser) -> list[ExamSummaryOut]:
    return [_summary_out(e) for e in exam_service.list_exams(db, user)]


@router.post("/exams", status_code=201)
def create_exam(data: ExamCreateIn, db: DbSession, user: CurrentUser) -> ExamDetailOut:
    exam = exam_service.create_exam(
        db,
        user,
        class_id=data.class_id,
        subject_code=data.subject_code,
        title=data.title,
        exam_date=data.exam_date,
    )
    db.refresh(exam)
    return _detail_out(exam)


@router.get("/exams/{exam_id}")
def get_exam(exam_id: int, db: DbSession, user: CurrentUser) -> ExamDetailOut:
    return _detail_out(exam_service.get_exam(db, user, exam_id))


@router.patch("/exams/{exam_id}")
def update_exam(
    exam_id: int, data: ExamUpdateIn, db: DbSession, user: CurrentUser
) -> ExamDetailOut:
    changes = {k: getattr(data, k) for k in data.model_fields_set}
    exam = exam_service.update_exam_details(db, user, exam_id, changes)
    db.flush()
    return _detail_out(exam)


@router.put("/exams/{exam_id}/mark-scheme")
def replace_mark_scheme(
    exam_id: int, data: MarkSchemeIn, db: DbSession, user: CurrentUser
) -> ExamDetailOut:
    exam, _ = exam_service.replace_mark_scheme(db, user, exam_id, data)
    db.flush()
    db.refresh(exam)
    return _detail_out(exam)


@router.put("/exams/{exam_id}/status")
def set_status(exam_id: int, data: ExamStatusIn, db: DbSession, user: CurrentUser) -> ExamDetailOut:
    exam = exam_service.set_status(db, user, exam_id, data.status)
    db.flush()
    return _detail_out(exam)


@router.delete("/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: int, db: DbSession, user: CurrentUser) -> None:
    exam_service.delete_exam(db, user, exam_id)


@router.post("/mark-scheme/import-preview")
async def import_preview(request: Request, user: CurrentUser) -> ImportPreviewOut:
    """Parse a CSV mark scheme sent as a raw text/csv body (D-020). Nothing is saved: the
    teacher reviews the result in the editor and saves it there."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in {"text/csv", "text/plain"}:
        raise ValidationFailedError("Send the file as text/csv", code="import.wrong_type")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_CSV_BYTES:
        raise ValidationFailedError(
            "File too large",
            code="import.too_large",
            issues=[Issue("import.too_large", params={"max_kb": MAX_CSV_BYTES // 1024})],
        )
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_CSV_BYTES:
            break
    text = decode_csv(bytes(body))
    if isinstance(text, Issue):
        return ImportPreviewOut(scheme=None, issues=[IssueOut.of(text)], validation=None)
    result = parse_mark_scheme_csv(text)
    return ImportPreviewOut(
        scheme=result.scheme,
        issues=[IssueOut.of(i) for i in result.issues],
        validation=_report_out(validate_mark_scheme(result.scheme)) if result.scheme else None,
    )
