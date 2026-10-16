"""Named answer sheets, unassigned spares and A4 stickers. QR payloads remain anonymous."""

import io
from pathlib import Path

import zxingcpp
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.types import ModelOutputInvalidError
from app.config import Settings
from app.db.models import AnswerSheet, Exam, IntakePage, Page, PageState, PrintJob, Student, User
from app.errors import ConflictError
from app.exports import fonts
from app.services import audit
from app.services.access import get_visible_exam
from app.services.cover_sheets import _require_not_draft
from app.sheets.cover_pdf import _draw_qr
from app.sheets.tokens import new_token, parse_payload, payload_for

HEADER_MM = 42


def prepare(
    db: Session, actor: User, exam_id: int, pages: int, spares: int, layout: str = "answer"
) -> list[AnswerSheet]:
    exam = get_visible_exam(db, actor, exam_id)
    _require_not_draft(exam)
    existing = list(db.scalars(select(AnswerSheet).where(AnswerSheet.exam_id == exam.id)))
    # Once any page arrives, issued page counts must stay stable for missing-page checks.
    received = db.scalar(
        select(Page.id)
        .join(AnswerSheet, Page.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.exam_id == exam.id)
        .limit(1)
    )
    if received and any(s.active and not s.spare and s.page_number > pages for s in existing):
        raise ConflictError("Cannot reduce pages after scanning", code="sheets.pages_locked")
    students = list(
        db.scalars(select(Student).where(Student.class_id == exam.class_id).order_by(Student.id))
    )
    found = {
        (s.student_id, s.page_number): s for s in existing if not s.spare and s.layout == layout
    }
    result = []
    for student in students:
        for number in range(1, pages + 1):
            sheet = found.get((student.id, number))
            if sheet is None:
                sheet = AnswerSheet(
                    exam_id=exam.id,
                    student_id=student.id,
                    page_number=number,
                    token=new_token(),
                    layout=layout,
                )
                db.add(sheet)
            sheet.active = True
            result.append(sheet)
    for sheet in existing:
        if not sheet.spare and sheet.layout == layout and sheet.page_number > pages:
            sheet.active = False
    for _ in range(spares):
        sheet = AnswerSheet(
            exam_id=exam.id,
            student_id=None,
            page_number=0,
            token=new_token(),
            spare=True,
            layout=layout,
        )
        db.add(sheet)
        result.append(sheet)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="prepare_answer_sheets",
        new_value={"pages_per_student": pages, "spares": spares},
    )
    return result


def fit(text: str, font: str, size: int, width: float) -> str:
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text + "…"


def document(db: Session, exam: Exam, sheets: list[AnswerSheet], layout: str) -> bytes:
    fonts.register()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for index, sheet in enumerate(sheets):
        student = db.get(Student, sheet.student_id) if sheet.student_id else None
        name = student.display_name or student.code if student else "Name / Nom: __________________"
        if layout == "labels":
            name = student.code if student else "Spare / Réserve"
            # A4 40-label format: 45.7 x 25.4 mm, four columns, ten rows.
            slot = index % 40
            if slot == 0 and index:
                canvas.showPage()
            x = (9.85 + (slot % 4) * 48.2) * mm
            y = A4[1] - (21.5 + (slot // 4 + 1) * 25.4) * mm
            _draw_qr(canvas, payload_for(sheet.token), x, y + 2 * mm, 21 * mm)
            canvas.setFont(fonts.REGULAR, 6)
            for n, text in enumerate(
                [
                    name[:22],
                    exam.school_class.name[:22],
                    exam.title[:22],
                    f"Page {sheet.page_number or '___'}",
                    student.code if student else "Spare / Réserve",
                ]
            ):
                canvas.drawString(
                    x + 22 * mm, y + (21 - n * 4) * mm, fit(text, fonts.REGULAR, 6, 23 * mm)
                )
            continue
        _draw_qr(canvas, payload_for(sheet.token), A4[0] - 40 * mm, A4[1] - 38 * mm, 28 * mm)
        canvas.setFont(fonts.BOLD, 13)
        canvas.drawString(15 * mm, A4[1] - 15 * mm, fit(name, fonts.BOLD, 13, 150 * mm))
        canvas.setFont(fonts.REGULAR, 9)
        canvas.drawString(
            15 * mm,
            A4[1] - 22 * mm,
            fit(f"{exam.school_class.name} · {exam.title}", fonts.REGULAR, 9, 150 * mm),
        )
        canvas.drawString(
            15 * mm,
            A4[1] - 29 * mm,
            f"Page {sheet.page_number or '____'} · "
            f"{student.code if student else 'Spare / Réserve'}",
        )
        canvas.setFont(fonts.REGULAR, 8)
        canvas.drawString(
            15 * mm,
            A4[1] - 37 * mm,
            "Blue or black pen, not pencil / Stylo bleu ou noir, pas de crayon",
        )
        canvas.setStrokeColorRGB(0.8, 0.8, 0.8)
        for offset in range(HEADER_MM + 8, 280, 8):
            canvas.line(15 * mm, A4[1] - offset * mm, A4[0] - 15 * mm, A4[1] - offset * mm)
        canvas.showPage()
    if layout == "labels" and sheets:
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def queue_document(
    db: Session,
    actor: User,
    exam: Exam,
    content: bytes,
    key: str,
    settings: Settings,
    send: bool = True,
) -> PrintJob:
    from app.services.scan_inbox import hardware

    config = hardware(db, actor.school_id)
    if send and not config.printer_uri:
        raise ConflictError("Configure a printer first", code="hardware.no_printer")
    existing = db.scalar(select(PrintJob).where(PrintJob.request_key == f"{actor.id}:{key}"))
    if existing:
        return existing
    job = PrintJob(
        school_id=actor.school_id,
        requested_by_id=actor.id,
        exam_id=exam.id,
        request_key=f"{actor.id}:{key}",
        kind="answer_sheets",
        status="queued" if send else "document_ready",
        language=actor.preferred_language.value,
        printer_uri=config.printer_uri,
        duplex=False,
        script_ids=[],
        confirmation_versions={},
    )
    db.add(job)
    db.flush()
    relative = Path("prints") / f"sheets-{job.id}.pdf"
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    job.file_path = relative.as_posix()
    audit.record(db, actor=actor, entity_type="print_job", entity_id=job.id, action="answer_sheets")
    return job


def readiness(db: Session, exam_id: int, student_id: int) -> tuple[list[int], bool]:
    expected = set(
        db.scalars(
            select(AnswerSheet.page_number).where(
                AnswerSheet.exam_id == exam_id,
                AnswerSheet.student_id == student_id,
                AnswerSheet.active.is_(True),
            )
        )
    )
    received = set(
        db.scalars(
            select(AnswerSheet.page_number)
            .join(Page, Page.answer_sheet_id == AnswerSheet.id)
            .where(
                AnswerSheet.exam_id == exam_id,
                AnswerSheet.student_id == student_id,
                Page.state == PageState.ASSIGNED,
            )
        )
    )
    problems = db.scalar(
        select(IntakePage.id)
        .join(AnswerSheet, IntakePage.answer_sheet_id == AnswerSheet.id)
        .where(
            AnswerSheet.exam_id == exam_id,
            or_(AnswerSheet.student_id == student_id, AnswerSheet.student_id.is_(None)),
            IntakePage.page_id.is_(None),
            IntakePage.discarded.is_(False),
        )
        .limit(1)
    )
    manual_problems = db.scalar(
        select(Page.id)
        .join(AnswerSheet, Page.answer_sheet_id == AnswerSheet.id)
        .where(
            AnswerSheet.exam_id == exam_id,
            or_(AnswerSheet.student_id == student_id, AnswerSheet.student_id.is_(None)),
            Page.state == PageState.UNASSIGNED,
        )
        .limit(1)
    )
    return sorted(expected - received), problems is not None or manual_problems is not None


def require_complete(db: Session, exam_id: int, student_id: int) -> None:
    missing, problems = readiness(db, exam_id, student_id)
    if missing or problems:
        raise ConflictError(
            "Resolve missing pages, duplicates and spares first", code="sheets.incomplete"
        )


def grading_image(db: Session, page: Page, settings: Settings) -> tuple[Path, int]:
    """Mask identifying header on an upright derivative; preserve the original scan."""
    original = settings.data_dir / page.image_path
    sheet = db.get(AnswerSheet, page.answer_sheet_id) if page.answer_sheet_id else None
    if sheet is None or sheet.layout == "labels":
        return original, page.effective_rotation
    target = settings.data_dir / "grading-pages" / f"{page.id}-{page.effective_rotation}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(original) as source:
        upright = source.convert("RGB").rotate(-page.effective_rotation, expand=True)
        bottom = round(upright.height * HEADER_MM / 297)
        for code in zxingcpp.read_barcodes(
            upright, formats=zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)
        ):
            if parse_payload(code.text).token == sheet.token:
                corners = code.position
                ys = [
                    corners.top_left.y,
                    corners.top_right.y,
                    corners.bottom_left.y,
                    corners.bottom_right.y,
                ]
                bottom = max(bottom, round(max(ys) + (max(ys) - min(ys)) * 0.25))
        if bottom > upright.height * 0.4:
            raise ModelOutputInvalidError("header_orientation_or_crop")
        ImageDraw.Draw(upright).rectangle((0, 0, upright.width, bottom), fill="white")
        upright.save(target)
    return target, 0
