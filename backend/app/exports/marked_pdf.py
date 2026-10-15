"""Marked PDFs (Phase 5): each scanned page, turned upright, with the marks in a margin column.

- The cover sheet carries the results box: total, marks per question and the teacher's comments.
- Each answer page lists the marks of the questions whose evidence is on that page. Where on the
  page an answer sits is not known (no question regions), so marks go in the margin rather than
  next to the words.
- Next to each question, one sign per mark scheme point, as teachers mark: ✓ full marks,
  ✗ no marks, the marks as a fraction when partly earned (owner, 2026-10-15).
- Students appear by code only: names are never printed on paper (non-negotiable).
- The stored page images are read, never changed.
- Text uses the bundled Noto fonts (app.exports.fonts).
"""

from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen.canvas import Canvas

from app.exports import fonts
from app.exports.labels import labels
from app.exports.notation import pretty
from app.marks import from_half_marks
from app.redpen.draw_pdf import draw_layout
from app.services.results import PointResult, QuestionResult, ScriptResult

PAGE_W, PAGE_H = A4
MARGIN = 10 * mm
HEADER = 10 * mm
COLUMN = 52 * mm
GAP = 4 * mm
FOOTER = 6 * mm
FONT = fonts.REGULAR
BOLD = fonts.BOLD


def _point_sign(point: PointResult) -> str:
    if point.final_half is None:
        return "-"
    if point.final_half >= point.max_half:
        return fonts.TICK
    if point.final_half == 0:
        return fonts.CROSS
    return f"({from_half_marks(point.final_half)}/{from_half_marks(point.max_half)})"


def _marks(question: QuestionResult) -> str:
    final = "-" if question.final_half is None else str(from_half_marks(question.final_half))
    signs = " ".join(_point_sign(p) for p in question.points)
    return f"{final} / {from_half_marks(question.question.max_half_marks)}   {signs}"


def _draw_image(
    canvas: Canvas, path: Path, rotation: int, box: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Draw the page upright, fitted in ``box``; returns where it landed (x, y, width, height)."""
    x, y, width, height = box
    with Image.open(path) as source:
        image = source.convert("RGB")
        if rotation % 360:
            image = image.rotate(-(rotation % 360), expand=True)
        scale = min(width / image.width, height / image.height)
        draw_w, draw_h = image.width * scale, image.height * scale
        left, bottom = x + (width - draw_w) / 2, y + height - draw_h
        canvas.drawImage(ImageReader(image), left, bottom, draw_w, draw_h)
        return left, bottom, draw_w, draw_h


class _Column:
    """Writes lines top-down in the margin column."""

    def __init__(self, canvas: Canvas) -> None:
        self.canvas = canvas
        self.x = PAGE_W - MARGIN - COLUMN
        self.y = PAGE_H - MARGIN - HEADER - 4 * mm

    def line(self, text: str, *, size: float = 10, bold: bool = False, gap: float = 1.4) -> None:
        font = BOLD if bold else FONT
        parts = [
            wrapped
            for paragraph in fonts.printable(text).split("\n")  # keep the writer's line breaks
            for wrapped in (simpleSplit(paragraph, font, size, COLUMN - 2 * mm) or [""])
        ]
        for part in parts:
            if self.y < MARGIN + size:
                return  # column full: the results box on the cover is the complete record
            fonts.draw(self.canvas, self.x + 1 * mm, self.y, part, font, size)
            self.y -= size * gap

    def space(self, amount: float = 3 * mm) -> None:
        self.y -= amount


def _footer(canvas: Canvas, result: ScriptResult, words: dict[str, str]) -> None:
    """On every page (owner, 2026-10-15): who reviewed and confirmed the marks."""
    teacher = result.confirmed_by_name or "-"
    canvas.setFillColorRGB(0.35, 0.35, 0.35)
    text = words["footer"].format(teacher=teacher)
    width = fonts.text_width(text, FONT, 8)
    fonts.draw(canvas, (PAGE_W - width) / 2, MARGIN / 2, text, FONT, 8)
    canvas.setFillColorRGB(0, 0, 0)


def draw_script(
    canvas: Canvas, result: ScriptResult, exam_title: str, data_dir: Path, language: str
) -> None:
    words = labels(language)
    code = result.script.student.code
    pages = result.pages
    # The cover carries the summary in a side column; answer pages give the scan the full width.
    cover_box = (
        MARGIN,
        MARGIN + FOOTER,
        PAGE_W - 2 * MARGIN - COLUMN - GAP,
        PAGE_H - 2 * MARGIN - HEADER - FOOTER,
    )
    answer_box = (
        MARGIN,
        MARGIN + FOOTER,
        PAGE_W - 2 * MARGIN,
        PAGE_H - 2 * MARGIN - HEADER - FOOTER,
    )
    for number, result_page in enumerate(pages, 1):
        page = result_page.page
        fonts.draw(
            canvas,
            MARGIN,
            PAGE_H - MARGIN - 5 * mm,
            f"{exam_title} · {code} · {words['page']} {number}/{len(pages)}",
            FONT,
            9,
        )
        if result.test_model:
            canvas.setFillColorRGB(0.75, 0.1, 0.1)
            canvas.setFont(BOLD, 11)
            canvas.drawRightString(
                PAGE_W - MARGIN,
                PAGE_H - MARGIN - 5 * mm,
                fonts.printable(words["test_model"].upper()),
            )
            canvas.setFillColorRGB(0, 0, 0)
        box = cover_box if page.is_cover else answer_box
        drawn = _draw_image(canvas, data_dir / page.image_path, page.effective_rotation, box)
        layout = result.red_pen.pages.get(page.id) if result.red_pen else None
        if layout is not None:
            draw_layout(canvas, layout, drawn)
        if page.is_cover:
            column = _Column(canvas)
            canvas.setStrokeColorRGB(0.6, 0.6, 0.6)
            canvas.line(
                column.x - GAP / 2, MARGIN + FOOTER, column.x - GAP / 2, PAGE_H - MARGIN - HEADER
            )
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
                    column.line(f"{question.question.label}: {pretty(question.comment)}", size=9)
        _footer(canvas, result, words)
        canvas.showPage()


def write_marked_pdf(
    out: BinaryIO,
    results: Iterable[ScriptResult],
    exam_title: str,
    data_dir: Path,
    language: str,
) -> int:
    """Write one PDF with every script in ``results``; returns the number of pages."""
    fonts.register()
    canvas = Canvas(out, pagesize=A4, pageCompression=1)
    canvas.setTitle(exam_title)
    canvas.setAuthor("Margin")
    pages = 0
    for result in results:
        draw_script(canvas, result, exam_title, data_dir, language)
        pages += len(result.pages)
    canvas.save()
    return pages
