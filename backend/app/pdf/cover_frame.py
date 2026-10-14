"""Detect the thick frame printed on cover sheets, without reading the QR codes.

Used to recognise a cover sheet whose QR codes are unreadable, so it is never mistaken for an
answer page and appended to the previous student's script.

Method (rotation-independent, tolerant of small skew and scanner offsets): on a small greyscale
copy, for each of the four sides, look at a band from 2 % to 12 % in from that edge. The side
counts as framed when at least 90 % of positions along it have a dark pixel somewhere in the band.
All four sides must be framed. Ruled answer paper fails because its lines cross the side bands
only at line positions; handwriting rarely fills a band along a whole side.
"""

from PIL import Image

_WORK_WIDTH = 300
_DARK = 100
_BAND = (0.02, 0.12)
_ALONG = (0.1, 0.9)  # ignore the corners, where sides meet
_REQUIRED_COVERAGE = 0.9


def has_cover_frame(image: Image.Image) -> bool:
    gray = image.convert("L")
    scale = _WORK_WIDTH / gray.width
    small = gray.resize((_WORK_WIDTH, max(1, round(gray.height * scale))))
    width, height = small.size
    pixels = small.load()
    if pixels is None:
        return False

    def dark(x: int, y: int) -> bool:
        value = pixels[x, y]
        return isinstance(value, int) and value < _DARK

    def side_framed(horizontal: bool, near_start: bool) -> bool:
        length, depth = (width, height) if horizontal else (height, width)
        band_from, band_to = int(depth * _BAND[0]), max(int(depth * _BAND[1]), 1)
        if near_start:
            band = range(band_from, band_to)
        else:
            band = range(depth - band_to, depth - band_from)
        positions = range(int(length * _ALONG[0]), int(length * _ALONG[1]))
        hits = 0
        for pos in positions:
            points = ((pos, d) for d in band) if horizontal else ((d, pos) for d in band)
            hits += any(dark(x, y) for x, y in points)
        return hits >= _REQUIRED_COVERAGE * len(positions)

    return all(
        side_framed(horizontal, near_start)
        for horizontal in (True, False)
        for near_start in (True, False)
    )
