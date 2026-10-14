"""Flag scripts whose page count is unusually far from the class's typical count (D-036).

A safety net for splitting mistakes the QR codes cannot catch, for example a cover sheet whose
codes and frame were both unreadable (its pages would join the previous student's script, making
that script unusually long, and leaving the real owner with none). The teacher checks flagged
scripts; nothing is changed automatically.
"""

from enum import StrEnum
from statistics import median_low

MIN_SCRIPTS_FOR_TYPICAL = 3
MIN_TOLERANCE = 2


class PageCountFlag(StrEnum):
    NO_ANSWER_PAGES = "no_answer_pages"
    MORE_THAN_USUAL = "more_than_usual"
    FEWER_THAN_USUAL = "fewer_than_usual"


def typical_page_count(counts: list[int]) -> int | None:
    """Median page count, or None when there are too few scripts to say what is typical."""
    if len(counts) < MIN_SCRIPTS_FOR_TYPICAL:
        return None
    return int(median_low(counts))


def page_count_flag(count: int, typical: int | None) -> PageCountFlag | None:
    """``count`` includes the cover sheet. Tolerance: half the typical count, at least 2 pages."""
    if count <= 1:
        return PageCountFlag.NO_ANSWER_PAGES
    if typical is None:
        return None
    tolerance = max(MIN_TOLERANCE, round(typical / 2))
    if count >= typical + tolerance:
        return PageCountFlag.MORE_THAN_USUAL
    if count <= typical - tolerance:
        return PageCountFlag.FEWER_THAN_USUAL
    return None
