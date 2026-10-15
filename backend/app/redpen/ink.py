"""Find the lines of handwriting on a page image with plain image processing (Pillow only).

The page is reduced to a fixed width, turned into ink / no ink with Otsu's threshold, and
measured row by row. Columns that are dark nearly all the way down (a printed margin line) are
ignored, as are rows covered almost edge to edge (a dark ruled line). Runs of rows with some ink
are the lines of writing. Everything is returned as fractions of the image, so callers can use
any resolution.
"""

from dataclasses import dataclass

from PIL import Image, ImageDraw

WIDTH = 800
MAX_THRESHOLD = 150  # never call light-grey paper texture ink
MIN_ROW_INK = 0.004  # share of a row that must be ink
MAX_ROW_INK = 0.6  # rows denser than this are ruled lines, not writing
MAX_COLUMN_INK = 0.5  # columns denser than this are printed margin lines
JOIN_GAP = 3  # rows; small gaps inside a line of writing (dots, descenders)
MIN_HEIGHT = 6  # rows; shorter runs are specks


@dataclass(frozen=True)
class Band:
    """One line of writing, as fractions of the image (0 at the top/left, 1 at the bottom/right)."""

    top: float
    bottom: float
    left: float
    right: float
    ink: float  # share of the band's area that is ink

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _otsu(hist: list[int]) -> int:
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, threshold, weight_b, sum_b = 0.0, 0, 0, 0.0
    for level in range(256):
        weight_b += hist[level]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += level * hist[level]
        mean_b, mean_f = sum_b / weight_b, (sum_all - sum_b) / weight_f
        between = weight_b * weight_f * (mean_b - mean_f) ** 2
        if between > best:
            best, threshold = between, level
    return threshold


def detect_lines(image: Image.Image) -> list[Band]:
    """Lines of writing on an upright page image, top to bottom."""
    gray = image.convert("L")
    scale = WIDTH / gray.width
    gray = gray.resize((WIDTH, max(1, round(gray.height * scale))))
    width, height = gray.size
    threshold = min(_otsu(gray.histogram()), MAX_THRESHOLD)
    ink = gray.point(lambda value: 255 if value < threshold else 0)

    # Blank out printed margin lines (columns dark nearly all the way down).
    draw = ImageDraw.Draw(ink)
    for x in range(width):
        if ink.crop((x, 0, x + 1, height)).histogram()[255] > MAX_COLUMN_INK * height:
            draw.line([(x, 0), (x, height - 1)], fill=0)

    active = []
    for y in range(height):
        share = ink.crop((0, y, width, y + 1)).histogram()[255] / width
        active.append(MIN_ROW_INK < share < MAX_ROW_INK)

    bands = []
    y = 0
    while y < height:
        if not active[y]:
            y += 1
            continue
        top = y
        gap = 0
        while y < height and gap <= JOIN_GAP:
            gap = 0 if active[y] else gap + 1
            y += 1
        bottom = y - gap
        if bottom - top >= MIN_HEIGHT:
            region = ink.crop((0, top, width, bottom))
            box = region.getbbox()
            if box is not None:
                left, _, right, _ = box
                area = (right - left) * (bottom - top)
                bands.append(
                    Band(
                        top=top / height,
                        bottom=bottom / height,
                        left=left / width,
                        right=right / width,
                        ink=region.histogram()[255] / area if area else 0.0,
                    )
                )
    return bands
