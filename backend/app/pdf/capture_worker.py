"""Bounded phone image preparation, executed outside the API/worker processes."""

import argparse
import json
import math
from pathlib import Path

import zxingcpp
from PIL import Image, ImageFilter, ImageOps


def prepare(source: Path, target: Path, options: dict[str, float | bool]) -> None:
    Image.MAX_IMAGE_PIXELS = 40_000_000
    with Image.open(source) as original:
        if original.format not in {"JPEG", "PNG", "TIFF", "WEBP"}:
            raise ValueError("image_type")
        if original.width * original.height > 40_000_000:
            raise ValueError("image_size")
        image = ImageOps.exif_transpose(original).convert("RGB")
    preview = image.copy()
    preview.thumbnail((1400, 1400))
    preview.save(target.with_name("original-preview.png"), "PNG")
    if options.get("auto_crop", True) and all(
        options.get(k, v) == v for k, v in {"left": 0, "top": 0, "right": 1, "bottom": 1}.items()
    ):
        small = ImageOps.grayscale(image)
        small.thumbnail((600, 600))
        mask = small.point(lambda value: 255 if value > 180 else 0).filter(
            ImageFilter.MedianFilter(7)
        )
        bounds = mask.getbbox()
        if bounds:
            x0, y0, x1, y1 = bounds
            fraction = (x1 - x0) * (y1 - y0) / (small.width * small.height)
            if 0.35 < fraction < 0.95 and x0 < small.width / 2 < x1 and y0 < small.height / 2 < y1:
                margin = 10
                image = image.crop(
                    (
                        max(0, x0 - margin) * image.width // small.width,
                        max(0, y0 - margin) * image.height // small.height,
                        min(small.width, x1 + margin) * image.width // small.width,
                        min(small.height, y1 + margin) * image.height // small.height,
                    )
                )
    width, height = image.size
    left, top = float(options.get("left", 0)), float(options.get("top", 0))
    right, bottom = float(options.get("right", 1)), float(options.get("bottom", 1))
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError("crop_bounds")
    image = image.crop(
        (round(left * width), round(top * height), round(right * width), round(bottom * height))
    )
    if min(image.size) < 200:
        raise ValueError("image_small")
    # QR geometry supplies the small skew; quarter-turn orientation remains the QR router's job.
    angle = float(options.get("angle", 0))
    if not math.isfinite(angle) or abs(angle) > 15:
        raise ValueError("angle")
    if options.get("auto_straighten", True) and angle == 0:
        small = image.copy()
        small.thumbnail((2000, 2000))
        codes = zxingcpp.read_barcodes(
            small, formats=zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)
        )
        if codes:
            p = codes[0].position
            slope = math.degrees(
                math.atan2(p.top_right.y - p.top_left.y, p.top_right.x - p.top_left.x)
            )
            residual = (slope + 45) % 90 - 45
            if abs(residual) <= 15:
                angle = residual
    if angle:
        image = image.rotate(
            angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white"
        )
    if options.get("clean", True):
        image = ImageOps.autocontrast(image, cutoff=0.5, preserve_tone=True)
    image.thumbnail((4200, 4200))
    image.save(target, "PNG")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--options", required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.input, args.output, json.loads(args.options.read_text(encoding="utf-8")))
    except Exception:
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
