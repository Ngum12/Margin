"""Build synthetic "scanned" PDFs for tests: cover sheets rendered to images, handwriting-like
answer pages, rotations, and damaged or erased QR codes."""

import io
import random
from dataclasses import dataclass, field

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from app.sheets.cover_pdf import FRAME_INSET_MM, FRAME_WIDTH_MM, QR_SIZE_MM

SCAN_DPI = 150
_PX_PER_MM = SCAN_DPI / 25.4


def render_pdf_pages(pdf: bytes, dpi: int = SCAN_DPI) -> list[Image.Image]:
    doc = pdfium.PdfDocument(pdf)
    try:
        return [doc[i].render(scale=dpi / 72).to_pil().convert("RGB") for i in range(len(doc))]
    finally:
        doc.close()


def answer_page(seed: int, lines: int = 18) -> Image.Image:
    """A ruled page with blue handwriting-like strokes (deterministic for a seed)."""
    rng = random.Random(seed)  # noqa: S311 - deterministic test data, not security
    width, height = round(210 * _PX_PER_MM), round(297 * _PX_PER_MM)
    image = Image.new("RGB", (width, height), (250, 250, 247))
    draw = ImageDraw.Draw(image)
    for y in range(round(30 * _PX_PER_MM), height - 20, round(9 * _PX_PER_MM)):
        draw.line([(0, y), (width, y)], fill=(170, 190, 215), width=1)
    draw.line([(round(28 * _PX_PER_MM), 0), (round(28 * _PX_PER_MM), height)], fill=(220, 120, 120))
    y = round(36 * _PX_PER_MM)
    for _ in range(lines):
        x = round(32 * _PX_PER_MM)
        while x < width - 60:
            word = rng.randint(20, 90)
            points = [(x + i * 4, y + rng.randint(-10, 3)) for i in range(word // 4)]
            if len(points) > 1:
                draw.line(points, fill=(30, 40, 140), width=2)
            x += word + rng.randint(12, 30)
        y += round(9 * _PX_PER_MM)
    return image.filter(ImageFilter.GaussianBlur(0.6))


def _qr_boxes(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Pixel boxes of the two QR codes on an upright cover page."""
    scale = image.width / 210
    margin = (FRAME_INSET_MM + FRAME_WIDTH_MM + 4) * scale
    size = QR_SIZE_MM * scale
    top_right = (image.width - margin - size, margin, image.width - margin, margin + size)
    bottom_left = (margin, image.height - margin - size, margin + size, image.height - margin)
    return [tuple(round(v) for v in box) for box in (top_right, bottom_left)]  # type: ignore[misc]


def damage_qr(cover: Image.Image) -> Image.Image:
    """White out the lower-right part of both QR codes: finder patterns stay, data is lost."""
    damaged = cover.copy()
    draw = ImageDraw.Draw(damaged)
    for x0, y0, x1, y1 in _qr_boxes(cover):
        w, h = x1 - x0, y1 - y0
        draw.rectangle([x0 + 0.42 * w, y0 + 0.42 * h, x1 - 0.1 * w, y1 - 0.1 * h], fill="white")
    return damaged


def erase_qr(cover: Image.Image) -> Image.Image:
    """Remove both QR codes completely (frame and text remain)."""
    erased = cover.copy()
    draw = ImageDraw.Draw(erased)
    for box in _qr_boxes(cover):
        draw.rectangle(box, fill="white")
    return erased


def erase_frame(cover: Image.Image) -> Image.Image:
    """Remove the thick frame (e.g. trimmed or washed out by the scanner)."""
    erased = cover.copy()
    draw = ImageDraw.Draw(erased)
    scale = cover.width / 210
    band = round((FRAME_INSET_MM + FRAME_WIDTH_MM + 1) * scale)
    w, h = cover.size
    for box in [(0, 0, w, band), (0, h - band, w, h), (0, 0, band, h), (w - band, 0, w, h)]:
        draw.rectangle(box, fill="white")
    return erased


@dataclass
class ScanPage:
    image: Image.Image
    # PDF /Rotate for this page (how a scanner may record orientation).
    pdf_rotation: int = 0


@dataclass
class ScanBuilder:
    pages: list[ScanPage] = field(default_factory=list)

    def add(self, image: Image.Image, *, rotate: int = 0, pdf_rotation: int = 0) -> "ScanBuilder":
        if rotate:
            image = image.rotate(rotate, expand=True)
        self.pages.append(ScanPage(image, pdf_rotation))
        return self

    def build(self) -> bytes:
        buffer = io.BytesIO()
        canvas = Canvas(buffer, pagesize=A4, invariant=True)
        for page in self.pages:
            width_pt = page.image.width / SCAN_DPI * 72
            height_pt = page.image.height / SCAN_DPI * 72
            canvas.setPageSize((width_pt, height_pt))
            # Set on every page: reportlab keeps the last rotation for following pages.
            canvas.setPageRotation(page.pdf_rotation)
            jpeg = io.BytesIO()
            page.image.save(jpeg, "JPEG", quality=85)
            jpeg.seek(0)
            canvas.drawImage(ImageReader(jpeg), 0, 0, width_pt, height_pt)
            canvas.showPage()
        canvas.save()
        return buffer.getvalue()
