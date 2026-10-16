"""Register-order report-card spreadsheets and scoped longitudinal results."""

import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Exam, ExamAbsence, Script, Student, User
from app.errors import NotFoundError
from app.marks import from_half_marks
from app.services import audit, roster
from app.services.access import visible_exams, visible_students
from app.services.results import exam_results, script_results


def safe_cell(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def excel(db: Session, actor: User, exam_id: int) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    found = exam_results(db, actor, exam_id)
    french = actor.preferred_language.value == "fr"
    book = Workbook()
    sheet = book.active
    sheet.title = "Résultats" if french else "Results"
    header = [
        "Code",
        "Nom" if french else "Name",
        "Matière" if french else "Subject",
        "Trimestre" if french else "Term",
        "Date",
        *[q.label for q in found.questions],
        "Total",
        "Maximum",
        "%",
        "Statut" if french else "Status",
    ]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    by_student = {r.script.student_id: r for r in found.scripts}
    absent = set(db.scalars(select(ExamAbsence.student_id).where(ExamAbsence.exam_id == exam_id)))
    registered = roster.exam_students(db, found.exam)
    roster_ids = {s.id for s in registered}
    registered.extend(
        r.script.student for r in found.scripts if r.script.student_id not in roster_ids
    )
    maximum = sum(q.max_half_marks for q in found.questions) / 2
    for student in registered:
        result = by_student.get(student.id)
        confirmed = bool(result and result.confirmed)
        marks = (
            [from_half_marks(q.final_half or 0) for q in result.questions]
            if result and confirmed
            else [None] * len(found.questions)
        )
        total = from_half_marks(result.total_half or 0) if result and confirmed else None
        status = (
            "Absent"
            if student.id in absent
            else ("Confirmé" if french else "Confirmed")
            if confirmed
            else ("En attente" if french else "Pending")
        )
        sheet.append(
            [
                safe_cell(student.code),
                safe_cell(student.display_name or ""),
                safe_cell(found.exam.subject_code),
                safe_cell(found.exam.term),
                found.exam.exam_date,
                *marks,
                total,
                maximum,
                round(float(total) * 100 / maximum, 1) if total is not None and maximum else None,
                status,
            ]
        )
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.column_dimensions["B"].width = 30
    sheet.print_options.horizontalCentered = True
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = "1:1"
    buffer = io.BytesIO()
    book.save(buffer)
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam_id,
        action="export_results_excel",
        new_value={"confirmed": len(found.confirmed)},
    )
    return buffer.getvalue()


def history(db: Session, actor: User, student_id: int) -> list[dict[str, Any]]:
    student = db.get(Student, student_id)
    if not student or student.school_id != actor.school_id:
        raise NotFoundError("Student")
    scripts = list(
        db.scalars(
            select(Script).where(
                Script.student_id == student_id,
                Script.exam_id.in_(visible_exams(actor).with_only_columns(Exam.id)),
            )
        )
    )
    if not scripts and not db.scalar(visible_students(actor).where(Student.id == student_id)):
        raise NotFoundError("Student")
    rows = []
    for script in scripts:
        exam = db.get_one(Exam, script.exam_id)
        result = script_results(db, exam, [script])[0]
        rows.append(
            {
                "exam_id": exam.id,
                "title": exam.title,
                "term": exam.term,
                "subject": exam.subject_code,
                "date": str(exam.exam_date or exam.created_at.date()),
                "academic_year": exam.school_class.academic_year,
                "total": from_half_marks(result.total_half or 0) if result.confirmed else None,
                "maximum": from_half_marks(result.max_half),
                "confirmed": result.confirmed,
            }
        )
    return sorted(rows, key=lambda r: (str(r["date"]), int(r["exam_id"])))
