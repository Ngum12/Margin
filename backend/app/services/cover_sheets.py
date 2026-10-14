"""Cover sheets: one stable random token per (exam, student) (D-029)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import CoverSheet, Exam, ExamStatus, Student, User
from app.errors import ConflictError
from app.services import audit
from app.services.access import get_visible_exam
from app.sheets.cover_pdf import SheetInfo, SheetStudent, build_cover_sheets_pdf
from app.sheets.tokens import new_token
from app.subjects.registry import get_registry


@dataclass(frozen=True)
class SheetRow:
    student: Student
    has_sheet: bool


def _require_not_draft(exam: Exam) -> None:
    if exam.status == ExamStatus.DRAFT:
        raise ConflictError(
            "Mark the exam as ready before printing cover sheets", code="exam.sheets_need_ready"
        )


def _class_students(db: Session, exam: Exam) -> list[Student]:
    return list(
        db.scalars(select(Student).where(Student.class_id == exam.class_id).order_by(Student.code))
    )


def _sheets_by_student(db: Session, exam: Exam) -> dict[int, CoverSheet]:
    sheets = db.scalars(select(CoverSheet).where(CoverSheet.exam_id == exam.id))
    return {s.student_id: s for s in sheets}


def list_sheets(db: Session, actor: User, exam_id: int) -> list[SheetRow]:
    exam = get_visible_exam(db, actor, exam_id)
    sheets = _sheets_by_student(db, exam)
    return [SheetRow(s, s.id in sheets) for s in _class_students(db, exam)]


def prepare_sheets(db: Session, actor: User, exam_id: int) -> list[SheetRow]:
    """Create sheets for students who have none. Existing tokens never change, so reprinting
    gives identical QR codes."""
    exam = get_visible_exam(db, actor, exam_id)
    _require_not_draft(exam)
    sheets = _sheets_by_student(db, exam)
    created = []
    for student in _class_students(db, exam):
        if student.id not in sheets:
            sheet = CoverSheet(exam_id=exam.id, student_id=student.id, token=new_token())
            db.add(sheet)
            created.append(student.code)
    try:
        db.flush()
    except IntegrityError as exc:  # pragma: no cover - 80-bit token collision
        raise ConflictError("Please try again", code="conflict") from exc
    if created:
        audit.record(
            db,
            actor=actor,
            entity_type="exam",
            entity_id=exam.id,
            action="prepare_cover_sheets",
            new_value={"student_codes": created},
        )
    return list_sheets(db, actor, exam_id)


def cover_sheets_pdf(db: Session, actor: User, exam_id: int) -> tuple[Exam, bytes]:
    exam = get_visible_exam(db, actor, exam_id)
    _require_not_draft(exam)
    sheets = _sheets_by_student(db, exam)
    students = [
        SheetStudent(code=s.code, token=sheets[s.id].token)
        for s in _class_students(db, exam)
        if s.id in sheets
    ]
    subject = get_registry().get(actor.school.curriculum, exam.subject_code)
    info = SheetInfo(
        exam_title=exam.title,
        subject_en=subject.names.en if subject else exam.subject_code,
        subject_fr=subject.names.fr if subject else exam.subject_code,
        class_name=exam.school_class.name,
        exam_date=exam.exam_date,
    )
    return exam, build_cover_sheets_pdf(info, students)
