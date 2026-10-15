"""Marked PDFs (Phase 5): each scanned page, turned upright, with the marks in a margin column.

- The cover sheet carries the results box: total, marks per question and the teacher's comments.
- Each answer page lists the marks of the questions whose evidence is on that page. Where on the
  page an answer sits is not known (no question regions), so marks go in the margin rather than
  next to the words.
- Students appear by code only: names are never printed on paper (non-negotiable).
- The stored page images are read, never changed.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen.canvas import Canvas

from app.exports.labels import labels
from app.marks import from_half_marks
from app.services.results import QuestionResult, ScriptResult

PAGE_W, PAGE_H = A4
MARGIN = 10 * mm
HEADER = 10 * mm
COLUMN = 52 * mm
GAP = 4 * mm
FONT = "Helvetica"
BOLD = "Helvetica-Bold"


def _text(value: str) -> str:
    """The built-in PDF fonts cover Windows-1252 (French included). Other characters (emoji,
    ticks) are left out: a "?" in their place would read like part of the comment."""
    return value.encode("cp1252", errors="ignore").decode("cp1252")


def _marks(question: QuestionResult) -> str:
    final = "-" if question.final_half is None else str(from_half_marks(question.final_half))
    return f"{final} / {from_half_marks(question.question.max_half_marks)}"


def _draw_image(
    canvas: Canvas, path: Path, rotation: int, box: tuple[float, float, float, float]
) -> None:
    x, y, width, height = box
    with Image.open(path) as source:
        image = source.convert("RGB")
        if rotation % 360:
            image = image.rotate(-(rotation % 360), expand=True)
        scale = min(width / image.width, height / image.height)
        draw_w, draw_h = image.width * scale, image.height * scale
        canvas.drawImage(
            ImageReader(image),
            x + (width - draw_w) / 2,
            y + height - draw_h,
            draw_w,
            draw_h,
        )


class _Column:
    """Writes lines top-down in the margin column."""

    def __init__(self, canvas: Canvas) -> None:
        self.canvas = canvas
        self.x = PAGE_W - MARGIN - COLUMN
        self.y = PAGE_H - MARGIN - HEADER - 4 * mm

    def line(self, text: str, *, size: float = 10, bold: bool = False, gap: float = 1.4) -> None:
        font = BOLD if bold else FONT
        for part in simpleSplit(_text(text), font, size, COLUMN - 2 * mm) or [""]:
            if self.y < MARGIN + size:
                return  # column full: the results box on the cover is the complete record
            self.canvas.setFont(font, size)
            self.canvas.drawString(self.x + 1 * mm, self.y, part)
            self.y -= size * gap

    def space(self, amount: float = 3 * mm) -> None:
        self.y -= amount


def _questions_by_page(result: ScriptResult) -> dict[int, list[QuestionResult]]:
    """Each question is shown on the first answer page that contains its evidence."""
    by_page: dict[int, list[QuestionResult]] = {}
    for question in result.questions:
        pages = result.pages_for_question(question.question.id)
        if pages:
            by_page.setdefault(pages[0], []).append(question)
    return by_page


def draw_script(
    canvas: Canvas, result: ScriptResult, exam_title: str, data_dir: Path, language: str
) -> None:
    words = labels(language)
    code = result.script.student.code
    by_page = _questions_by_page(result)
    pages = result.pages
    image_box = (MARGIN, MARGIN, PAGE_W - 2 * MARGIN - COLUMN - GAP, PAGE_H - 2 * MARGIN - HEADER)
    for number, result_page in enumerate(pages, 1):
        page = result_page.page
        canvas.setFont(FONT, 9)
        canvas.drawString(
            MARGIN,
            PAGE_H - MARGIN - 5 * mm,
            _text(f"{exam_title} · {code} · {words['page']} {number}/{len(pages)}"),
        )
        _draw_image(canvas, data_dir / page.image_path, page.effective_rotation, image_box)
        column = _Column(canvas)
        canvas.setStrokeColorRGB(0.6, 0.6, 0.6)
        canvas.line(column.x - GAP / 2, MARGIN, column.x - GAP / 2, PAGE_H - MARGIN - HEADER)
        if page.is_cover:
            column.line(words["results"], size=12, bold=True)
            column.line(code, size=11)
            column.space()
            total = result.total_half or 0
            column.line(
                f"{words['total']}: {from_half_marks(total)} / {from_half_marks(result.max_half)}",
                size=14,
                bold=True,
            )
            column.space()
            for question in result.questions:
                column.line(f"{question.question.label}   {_marks(question)}")
            comments = [q for q in result.questions if q.comment]
            if comments:
                column.space()
                column.line(words["comments"], bold=True)
                for question in comments:
                    column.line(f"{question.question.label}: {question.comment}", size=9)
        else:
            here = by_page.get(page.id, [])
            if here:
                column.line(words["marks_here"], size=9, bold=True)
                column.space(1 * mm)
                for question in here:
                    column.line(
                        f"{question.question.label}   {_marks(question)}", size=12, bold=True
                    )
            else:
                column.line(words["not_marked"], size=8)
        canvas.showPage()


def write_marked_pdf(
    out: BinaryIO,
    results: Iterable[ScriptResult],
    exam_title: str,
    data_dir: Path,
    language: str,
) -> int:
    """Write one PDF with every script in ``results``; returns the number of pages."""
    canvas = Canvas(out, pagesize=A4, pageCompression=1)
    canvas.setTitle(_text(exam_title))
    canvas.setAuthor("Margin")
    pages = 0
    for result in results:
        draw_script(canvas, result, exam_title, data_dir, language)
        pages += len(result.pages)
    canvas.save()
    return pages
