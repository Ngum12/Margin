"""Fonts for marked PDFs (owner, 2026-10-15): Noto Sans for text (all French characters) and
Noto Sans Symbols 2 for ✓ and ✗, both under the SIL Open Font License 1.1 and bundled in
``fonts/`` (see ``fonts/fonts.json``). Characters neither font has (emoji) are left out rather
than printed as a box or "?"."""

import json
from functools import cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

FONT_DIR = Path(__file__).parent / "fonts"
REGULAR = "NotoSans"
BOLD = "NotoSans-Bold"
SYMBOLS = "NotoSansSymbols2"
# Pen-like handwriting for the red pen: comments, scores and the total (approved 2026-10-15).
HANDWRITING = "Caveat"
TICK = "✓"
CROSS = "✗"

_FILES = {
    REGULAR: "NotoSans-Regular.ttf",
    BOLD: "NotoSans-Bold.ttf",
    SYMBOLS: "NotoSansSymbols2-Regular.ttf",
    HANDWRITING: "Caveat-Regular.ttf",
}


def manifest() -> list[dict[str, object]]:
    data: list[dict[str, object]] = json.loads(
        (FONT_DIR / "fonts.json").read_text(encoding="utf-8")
    )
    return data


@cache
def register() -> None:
    """Register the bundled fonts with ReportLab (once per process)."""
    for name, filename in _FILES.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))


@cache
def _covered(font: str) -> frozenset[int]:
    register()
    face = pdfmetrics.getFont(font).face
    return frozenset(face.charToGlyph)


def printable(text: str) -> str:
    """The text without characters that no bundled font can print."""
    text_chars, symbol_chars = _covered(REGULAR), _covered(SYMBOLS)
    return "".join(c for c in text if c in "\n\t" or ord(c) in text_chars or ord(c) in symbol_chars)


def draw(canvas: Canvas, x: float, y: float, text: str, font: str, size: float) -> float:
    """Draw ``text`` starting at (x, y), switching to the symbol font for characters the text
    font lacks (✓, ✗). Returns the x position after the text."""
    text_chars, symbol_chars = _covered(font), _covered(SYMBOLS)
    run, run_font = "", font
    for char in text:
        code = ord(char)
        wanted = font if code in text_chars else SYMBOLS if code in symbol_chars else None
        if wanted is None:
            continue
        if wanted != run_font and run:
            canvas.setFont(run_font, size)
            canvas.drawString(x, y, run)
            x += pdfmetrics.stringWidth(run, run_font, size)
            run = ""
        run_font = wanted
        run += char
    if run:
        canvas.setFont(run_font, size)
        canvas.drawString(x, y, run)
        x += pdfmetrics.stringWidth(run, run_font, size)
    return x
