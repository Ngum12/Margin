"""Child process that renders an uploaded PDF and reads its cover-sheet QR codes (D-028).

Run only by app.pdf.runner, never inside the web server process. A crash, hang or memory blow-up
in PDFium or the QR decoder then kills only this process.

    python -m app.pdf.render_worker --input original.pdf --output-dir pages/ --dpi 200 ...

Writes one JPEG and one thumbnail per page, then ``manifest.json`` last. Exit codes:
0 ok, 2 the PDF cannot be opened or a page cannot be rendered, 3 too many pages, 4 bad arguments.
Nothing is logged about page content.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import zxingcpp
from PIL import Image

from app.pdf.cover_frame import has_cover_frame

EXIT_OK = 0
EXIT_UNREADABLE = 2
EXIT_TOO_MANY_PAGES = 3
EXIT_BAD_ARGS = 4

MANIFEST_NAME = "manifest.json"
THUMB_WIDTH = 400


def _read_qr(image: Image.Image) -> dict[str, Any]:
    results = zxingcpp.read_barcodes(
        image, formats=zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode), return_errors=True
    )
    valid = [b for b in results if b.valid]
    return {
        "texts": sorted({b.text for b in valid}),
        "orientation": valid[0].orientation if valid else 0,
        "damaged": sum(1 for b in results if not b.valid),
    }


def render(
    input_path: Path,
    output_dir: Path,
    *,
    dpi: int,
    quality: int,
    max_pages: int,
    max_pixels: int,
) -> dict[str, Any]:
    pdf = pdfium.PdfDocument(input_path)
    try:
        page_count = len(pdf)
        if page_count > max_pages:
            raise _TooManyPagesError(page_count)
        pages = []
        for index in range(page_count):
            page = pdf[index]
            width_pt, height_pt = page.get_size()
            scale = dpi / 72
            if width_pt * height_pt * scale * scale > max_pixels:
                scale = math.sqrt(max_pixels / (width_pt * height_pt))
            # pypdfium2 does not apply the page's own /Rotate unless asked; scanners use it to
            # record orientation, so render the page the way a PDF viewer shows it.
            image = page.render(scale=scale, rotation=page.get_rotation()).to_pil().convert("RGB")
            page.close()

            qr = _read_qr(image)
            # The stored image is never turned (Phase 4, D-049). A cover sheet's QR orientation
            # gives the clockwise turn that makes it upright; the app applies it when showing
            # the page and before transcription, and carries it to the pages that follow.
            qr_rotation = 0
            if qr["texts"] and qr["orientation"]:
                qr_rotation = (-int(qr["orientation"])) % 360
            frame = has_cover_frame(image)

            name = f"{index:04d}.jpg"
            image.save(output_dir / name, "JPEG", quality=quality, optimize=True)
            thumb = image.copy()
            thumb.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 2))
            thumb.save(output_dir / f"thumb_{name}", "JPEG", quality=80, optimize=True)
            pages.append(
                {
                    "index": index,
                    "image": name,
                    "thumb": f"thumb_{name}",
                    "width": image.width,
                    "height": image.height,
                    "qr_rotation": qr_rotation,
                    "qr_texts": qr["texts"],
                    "qr_damaged": qr["damaged"],
                    "cover_frame": frame,
                }
            )
        return {"page_count": page_count, "pages": pages}
    finally:
        pdf.close()


class _TooManyPagesError(Exception):
    def __init__(self, count: int) -> None:
        super().__init__(count)
        self.count = count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dpi", type=int, required=True)
    parser.add_argument("--quality", type=int, required=True)
    parser.add_argument("--max-pages", type=int, required=True)
    parser.add_argument("--max-pixels", type=int, default=40_000_000)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_BAD_ARGS

    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        manifest = render(
            args.input,
            args.output_dir,
            dpi=args.dpi,
            quality=args.quality,
            max_pages=args.max_pages,
            max_pixels=args.max_pixels,
        )
    except _TooManyPagesError as exc:
        print(json.dumps({"error": "too_many_pages", "page_count": exc.count}), file=sys.stderr)
        return EXIT_TOO_MANY_PAGES
    except (pdfium.PdfiumError, OSError, ValueError) as exc:
        print(json.dumps({"error": "unreadable", "type": type(exc).__name__}), file=sys.stderr)
        return EXIT_UNREADABLE

    # Write the manifest last and atomically: its presence means every page was written.
    tmp = args.output_dir / (MANIFEST_NAME + ".tmp")
    tmp.write_text(json.dumps(manifest), encoding="utf-8")
    os.replace(tmp, args.output_dir / MANIFEST_NAME)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
