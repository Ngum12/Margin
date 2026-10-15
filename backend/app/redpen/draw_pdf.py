"""Draw a red pen layout onto a PDF page, over the scanned image.

Ticks and crosses are pen strokes, not font characters: a tick has a short down stroke and a
long rising stroke, as a teacher draws it (owner, 2026-10-15: "elongated" ticks). Scores,
comments and the circled total are in the Caveat handwriting font, in red.
"""

from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

from app.exports import fonts
from app.redpen.layout import CROSS, PARTIAL, TICK, Mark, PageLayout

RED = (0.82, 0.07, 0.07)


def _stroke(canvas: Canvas, size: float) -> None:
    canvas.setStrokeColorRGB(*RED)
    canvas.setFillColorRGB(*RED)
    canvas.setLineWidth(max(1.3, size * 0.085))
    canvas.setLineCap(1)
    canvas.setLineJoin(1)


def draw_tick(canvas: Canvas, x: float, y: float, size: float) -> float:
    """Tick starting at (x, y) (PDF points, y up). Returns its right edge."""
    _stroke(canvas, size)
    path = canvas.beginPath()
    path.moveTo(x, y + size * 0.05)
    path.lineTo(x + size * 0.28, y - size * 0.35)
    path.lineTo(x + size * 0.95, y + size * 0.62)
    canvas.drawPath(path, stroke=1, fill=0)
    return x + size * 0.95


def draw_cross(canvas: Canvas, x: float, y: float, size: float) -> float:
    _stroke(canvas, size)
    half = size * 0.3
    canvas.line(x, y - half, x + size * 0.6, y + half)
    canvas.line(x, y + half, x + size * 0.6, y - half)
    return x + size * 0.6


def draw_layout(canvas: Canvas, layout: PageLayout, box: tuple[float, float, float, float]) -> None:
    """``box`` is where the page image was drawn: (x, y, width, height) in PDF points."""
    if not layout.placed:
        return
    fonts.register()
    x0, y0, width, height = box

    def at(mark: Mark) -> tuple[float, float, float]:
        return x0 + mark.x * width, y0 + (1 - mark.y) * height, mark.size * height

    canvas.saveState()
    for mark in layout.marks:
        if mark.pending:
            continue  # only teacher decisions are printed
        x, y, size = at(mark)
        if mark.kind == TICK:
            draw_tick(canvas, x, y, size)
        elif mark.kind == CROSS:
            draw_cross(canvas, x, y, size)
        elif mark.kind == PARTIAL:
            right = draw_tick(canvas, x, y, size)
            canvas.setFont(fonts.HANDWRITING, size * 0.55)
            canvas.drawString(right + size * 0.08, y - size * 0.1, mark.text)
        elif mark.kind == "score":
            canvas.setFillColorRGB(*RED)
            canvas.setFont(fonts.HANDWRITING, size * 0.95)
            canvas.drawRightString(x, y - size * 0.3, mark.text)
        elif mark.kind == "total":
            canvas.setFillColorRGB(*RED)
            _stroke(canvas, size * 0.7)
            font_size = size * 0.95
            text_width = canvas.stringWidth(mark.text, fonts.HANDWRITING, font_size)
            canvas.ellipse(
                x - size * 0.35,
                y - size * 0.6,
                x + text_width + size * 0.35,
                y + size * 0.55,
                stroke=1,
                fill=0,
            )
            canvas.setFont(fonts.HANDWRITING, font_size)
            canvas.drawString(x, y - size * 0.3, mark.text)
        elif mark.kind == "comment":
            canvas.setFillColorRGB(*RED)
            font_size = max(9.0, size * 1.0)
            canvas.setFont(fonts.HANDWRITING, font_size)
            lines = [
                part
                for paragraph in fonts.printable(mark.text).split("\n")
                for part in (
                    simpleSplit(paragraph, fonts.HANDWRITING, font_size, mark.width * width) or [""]
                )
            ][:3]
            for number, line in enumerate(lines):
                canvas.drawString(x, y - font_size * (0.9 + number * 1.05), line)
    canvas.restoreState()
