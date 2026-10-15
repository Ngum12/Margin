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


# Arrows no bundled font has: drawn as pen strokes in the text's colour (width in em).
VECTOR_GLYPHS = {"→": 1.0, "⇌": 1.0}  # → and ⇌


def _font_for(char: str, font: str) -> str | None:
    """The first font that has ``char``: the requested one, then Noto Sans, then symbols."""
    code = ord(char)
    for candidate in (font, REGULAR, SYMBOLS):
        if code in _covered(candidate):
            return candidate
    return None


def printable(text: str, font: str = REGULAR) -> str:
    """The text without characters that no bundled font can print (emoji)."""
    return "".join(
        c for c in text if c in "\n\t" or c in VECTOR_GLYPHS or _font_for(c, font) is not None
    )


def _arrow(canvas: Canvas, x: float, y: float, size: float, char: str) -> float:
    width = size * VECTOR_GLYPHS[char]
    mid = y + size * 0.3
    canvas.saveState()
    canvas.setLineWidth(max(0.6, size * 0.07))
    canvas.setLineCap(1)
    if char == "→":
        canvas.line(x + size * 0.1, mid, x + width - size * 0.1, mid)
        canvas.line(x + width - size * 0.32, mid + size * 0.18, x + width - size * 0.1, mid)
        canvas.line(x + width - size * 0.32, mid - size * 0.18, x + width - size * 0.1, mid)
    else:  # ⇌: a harpoon each way
        top, bottom = mid + size * 0.1, mid - size * 0.1
        canvas.line(x + size * 0.1, top, x + width - size * 0.1, top)
        canvas.line(x + width - size * 0.32, top + size * 0.18, x + width - size * 0.1, top)
        canvas.line(x + size * 0.1, bottom, x + width - size * 0.1, bottom)
        canvas.line(x + size * 0.32, bottom - size * 0.18, x + size * 0.1, bottom)
    canvas.restoreState()
    return x + width


def text_width(text: str, font: str, size: float) -> float:
    total = 0.0
    for char in text:
        if char in VECTOR_GLYPHS:
            total += size * VECTOR_GLYPHS[char]
        else:
            chosen = _font_for(char, font)
            if chosen is not None:
                total += pdfmetrics.stringWidth(char, chosen, size)
    return total


def draw(canvas: Canvas, x: float, y: float, text: str, font: str, size: float) -> float:
    """Draw ``text`` from (x, y), falling back character by character to Noto Sans and then to
    Noto Sans Symbols 2 (✓, ✗), and drawing → and ⇌ as strokes. Returns the x after the text."""
    run, run_font = "", font

    def flush() -> None:
        nonlocal x, run
        if run:
            canvas.setFont(run_font, size)
            canvas.drawString(x, y, run)
            x += pdfmetrics.stringWidth(run, run_font, size)
            run = ""

    for char in text:
        if char in VECTOR_GLYPHS:
            flush()
            x = _arrow(canvas, x, y, size, char)
            continue
        wanted = _font_for(char, font)
        if wanted is None:
            continue
        if wanted != run_font:
            flush()
            run_font = wanted
        run += char
    flush()
    return x
