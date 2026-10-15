"""Decide where the red pen marks go on one answer page. Pure: no database, no files.

Positions are fractions of the upright page (x to the right, y down), so the PDF and the screen
draw the same layout at any size.

- A point that earned marks: a long tick just after the end of the last line holding its
  evidence (several on one line are spaced along it).
- A point that earned nothing: a cross after the question's first line.
- The question's score, in the left margin beside its first line.
- The teacher's comment, written in the blank space below the question's answer when there is
  room, otherwise left for the margin column.
- The total, circled, at the top of the first answer page.
"""

import re
from dataclasses import dataclass, field, replace

from app.redpen.align import Alignment
from app.redpen.ink import Band

TICK = "tick"
CROSS = "cross"
PARTIAL = "partial"


@dataclass(frozen=True)
class PointMark:
    point_id: int
    sign: str  # tick, cross or partial
    earned: str  # "1/2" for a partial point, "" otherwise
    refs: tuple[int, ...]  # line indexes on this page holding the evidence
    pending: bool = False  # from the AI's proposal, not yet a teacher decision


@dataclass(frozen=True)
class QuestionMarks:
    question_id: int
    label: str
    score: str  # "2/3"
    points: tuple[PointMark, ...]
    comment: str = ""


@dataclass(frozen=True)
class Mark:
    kind: str  # tick, cross, partial, score, comment, total
    x: float
    y: float
    size: float  # height of the mark, as a fraction of the page height
    text: str = ""
    width: float = 0.0  # comment box width (fraction of page width)
    question_id: int | None = None
    point_id: int | None = None
    pending: bool = False


@dataclass
class PageLayout:
    placed: bool  # the red pen could be placed on this page
    marks: list[Mark] = field(default_factory=list)
    # Comments that found no room below their answer (printed in the margin column instead).
    unplaced_comments: list[QuestionMarks] = field(default_factory=list)


def label_key(text: str) -> str:
    """ "1(a)", "1a", "1 a)", "Q1(a)." all become "1a"."""
    return re.sub(r"[^0-9a-z]", "", text.lower().removeprefix("q"))


def question_starts(text_lines: list[str], labels: list[str]) -> dict[str, int]:
    """Line index where each question's answer begins on this page (its label written first)."""
    keys = {label_key(label): label for label in labels}
    found: dict[str, int] = {}
    for index, line in enumerate(text_lines):
        written = re.match(
            r"\s*(?:q\s*)?(\d+\s*\(?\s*[a-z]?\s*\)?(?:\s*\(?\s*[ivx]+\s*\))?)", line.lower()
        )
        if not written:
            continue
        key = label_key(written.group(1))
        # Longest label first: "1a" must not be taken as "1" when both exist.
        for candidate in sorted(keys, key=len, reverse=True):
            if key.startswith(candidate) and keys[candidate] not in found:
                rest = key[len(candidate) :]
                if not rest or not rest[0].isdigit():
                    found[keys[candidate]] = index
                break
    return found


def _band_for_line(alignment: Alignment, bands: list[Band], line: int) -> tuple[Band, Band] | None:
    span = alignment.lines.get(line)
    if span is None:
        return None
    return bands[span[0]], bands[span[1]]


def layout_page(
    text_lines: list[str],
    bands: list[Band],
    alignment: Alignment | None,
    questions: list[QuestionMarks],
    *,
    total: str | None = None,
) -> PageLayout:
    """``questions`` are those whose answer starts on this page or has evidence on it."""
    if alignment is None or not alignment.confident or not bands:
        return PageLayout(placed=False, unplaced_comments=[q for q in questions if q.comment])

    layout = PageLayout(placed=True)
    line_height = sum(b.height for b in bands) / len(bands)
    size = min(max(line_height * 1.6, 0.025), 0.06)  # long, confident strokes
    step = size * 1.15  # room for a full tick between marks on one line
    starts = question_starts(text_lines, [q.label for q in questions])
    # Marks waiting for their line: placed together at the end so they can be spaced to fit.
    waiting: dict[int, list[Mark]] = {}

    def place(band_index: int, mark: Mark) -> None:
        waiting.setdefault(band_index, []).append(mark)

    band_of_line = dict(alignment.lines)
    for question in questions:
        start_line = starts.get(question.label)
        start_span = band_of_line.get(start_line) if start_line is not None else None
        for point in question.points:
            target: int | None = None
            if point.sign != CROSS:
                spans = [band_of_line[r] for r in point.refs if r in band_of_line]
                if spans:
                    target = max(span[1] for span in spans)
            if target is None and start_span is not None:
                target = start_span[0]
            if target is None:
                continue
            band = bands[target]
            place(
                target,
                Mark(
                    kind=point.sign,
                    x=0.0,
                    y=(band.top + band.bottom) / 2,
                    size=size,
                    text=point.earned,
                    question_id=question.question_id,
                    point_id=point.point_id,
                    pending=point.pending,
                ),
            )
        if start_span is not None:
            first = bands[start_span[0]]
            layout.marks.append(
                Mark(
                    kind="score",
                    x=max(first.left - 0.015, 0.01),
                    y=(first.top + first.bottom) / 2,
                    size=size * 0.8,
                    text=question.score,
                    question_id=question.question_id,
                )
            )
        if question.comment:
            spot = _comment_spot(question, starts, start_line, band_of_line, bands, line_height)
            if spot is None:
                layout.unplaced_comments.append(question)
            else:
                x, y, width = spot
                layout.marks.append(
                    Mark(
                        kind="comment",
                        x=x,
                        y=y,
                        size=line_height * 1.1,
                        text=question.comment,
                        width=width,
                        question_id=question.question_id,
                    )
                )
    for band_index, marks in waiting.items():
        band = bands[band_index]
        start = band.right + 0.02
        dy = 0.0
        if start + len(marks) * step > 0.985:
            # The line runs to the edge: put the marks just below its end, on the ruled line,
            # rather than over the student's words.
            start = max(0.985 - len(marks) * step, band.left)
            dy = band.height * 0.75
        layout.marks.extend(
            replace(mark, x=start + number * step, y=mark.y + dy)
            for number, mark in enumerate(marks)
        )
    if total is not None:
        top = bands[0]
        layout.marks.append(
            Mark(kind="total", x=0.86, y=max(top.top - 0.035, 0.035), size=size, text=total)
        )
    return layout


def _comment_spot(
    question: QuestionMarks,
    starts: dict[str, int],
    start_line: int | None,
    band_of_line: dict[int, tuple[int, int]],
    bands: list[Band],
    line_height: float,
) -> tuple[float, float, float] | None:
    """Blank space below the question's answer, before the next answer: (x, y, width)."""
    if start_line is None or start_line not in band_of_line:
        return None
    later = sorted(line for line in starts.values() if line > start_line)
    end_line = later[0] if later else None
    own = [
        span
        for line, span in band_of_line.items()
        if line >= start_line and (end_line is None or line < end_line)
    ]
    last_band = max(span[1] for span in own)
    below = bands[last_band].bottom
    next_top = bands[last_band + 1].top if last_band + 1 < len(bands) else 0.97
    lines_needed = max(1, min(3, len(question.comment) // 45 + 1))
    left = bands[band_of_line[start_line][0]].left
    # 1. Blank space below the answer.
    if next_top - below >= line_height * (1.4 * lines_needed + 0.4):
        return left, below + line_height * 0.3, 0.9 - left
    # 2. Room to the right of the answer's last line (after the ticks), on that line.
    end = bands[last_band].right + 0.22
    if end < 0.6 and len(question.comment) <= 70:
        return end, bands[last_band].top - line_height * 0.15, 0.95 - end
    return None
