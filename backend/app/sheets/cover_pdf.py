"""Printable cover sheets (reportlab). One A4 page per student.

Layout choices that the upload pipeline relies on:
- A thick black frame inset from the page edge (``FRAME_INSET_MM``), so a cover sheet is
  recognisable even when both QR codes are unreadable (see app.pdf.cover_frame).
- The same QR code twice, at opposite corners, at error-correction level H.
- No real names: students appear only by their pseudonymous code.
"""

import io
from dataclasses import dataclass
from datetime import date

import segno
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from app.sheets.tokens import payload_for

FRAME_INSET_MM = 10
FRAME_WIDTH_MM = 4
QR_SIZE_MM = 42
QR_QUIET_ZONE_MODULES = 4


@dataclass(frozen=True)
class SheetInfo:
    exam_title: str
    subject_en: str
    subject_fr: str
    class_name: str
    exam_date: date | None


@dataclass(frozen=True)
class SheetStudent:
    code: str
    token: str


def _draw_qr(canvas: Canvas, payload: str, x: float, y: float, size: float) -> None:
    """Draw the QR as vector squares with its quiet zone inside ``size`` (bottom-left at x, y)."""
    qr = segno.make(payload, error="h", micro=False, boost_error=False)
    rows = [list(row) for row in qr.matrix]
    modules = len(rows) + 2 * QR_QUIET_ZONE_MODULES
    cell = size / modules
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(x, y, size, size, stroke=0, fill=1)
    canvas.setFillColorRGB(0, 0, 0)
    for r, row in enumerate(rows):
        for c, dark in enumerate(row):
            if dark:
                canvas.rect(
                    x + (c + QR_QUIET_ZONE_MODULES) * cell,
                    y + size - (r + QR_QUIET_ZONE_MODULES + 1) * cell,
                    cell,
                    cell,
                    stroke=0,
                    fill=1,
                )


def _draw_sheet(canvas: Canvas, info: SheetInfo, student: SheetStudent) -> None:
    width, height = A4
    inset = FRAME_INSET_MM * mm
    canvas.setLineWidth(FRAME_WIDTH_MM * mm)
    canvas.rect(inset, inset, width - 2 * inset, height - 2 * inset, stroke=1, fill=0)

    payload = payload_for(student.token)
    qr = QR_SIZE_MM * mm
    margin = inset + FRAME_WIDTH_MM * mm + 4 * mm
    _draw_qr(canvas, payload, width - margin - qr, height - margin - qr, qr)
    _draw_qr(canvas, payload, margin, margin, qr)

    left = margin
    top = height - margin
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(left, top - 8 * mm, "COVER SHEET")
    canvas.setFont("Helvetica", 13)
    canvas.drawString(left, top - 15 * mm, "FICHE DE COUVERTURE")

    canvas.setFont("Helvetica", 12)
    canvas.drawString(left, top - 60 * mm, "Student code / Code élève")
    canvas.setFont("Helvetica-Bold", 54)
    canvas.drawString(left, top - 82 * mm, student.code)

    lines = [
        ("Exam / Examen", info.exam_title),
        ("Subject / Matière", f"{info.subject_en} / {info.subject_fr}"),
        ("Class / Classe", info.class_name),
        ("Date", info.exam_date.isoformat() if info.exam_date else ""),
    ]
    y = top - 105 * mm
    for label, value in lines:
        canvas.setFont("Helvetica", 11)
        canvas.drawString(left, y, label)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(left + 45 * mm, y, value[:70])
        y -= 11 * mm

    instructions = [
        "Put this sheet on top of your answer pages. "
        "Do not write on it, fold it or cover the codes.",
        "Placez cette fiche sur vos copies. N'écrivez pas dessus, ne la pliez pas et ne cachez pas",
        "les codes.",
    ]
    canvas.setFont("Helvetica", 10.5)
    y -= 6 * mm
    for line in instructions:
        canvas.drawString(left, y, line)
        y -= 6 * mm


def build_cover_sheets_pdf(info: SheetInfo, students: list[SheetStudent]) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4, invariant=True)
    canvas.setTitle(f"Cover sheets - {info.exam_title}")
    canvas.setCreator("Marking Assistant")
    for student in students:
        _draw_sheet(canvas, info, student)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()
