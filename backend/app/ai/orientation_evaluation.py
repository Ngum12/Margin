"""Evaluate the Reader's orientation judgement (Phase 4, owner change 1).

Each labelled page (upright) is also fed turned 90, 180 and 270 degrees clockwise, in memory; the
stored files are never changed. Extra pages with a known orientation (for example the owner's
upside-down test page) can be added. Every judgement is classed as:

- ``fixed``: the page was not upright and the judgement would turn it back correctly;
- ``left``: the page was upright and nothing would be turned;
- ``wrong``: a confident judgement (at least the threshold) that would turn the page the wrong
  way, or turn an upright page: the harmful case;
- ``missed``: the page was not upright but nothing would be turned (judged upright, low
  confidence, or no valid judgement).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.ai.eval_cache import EvalCache
from app.ai.types import ModelOutputInvalidError, ModelUnavailableError, PageImage, Reader
from app.ai.validation import ORIENTATION_TURN
from app.subjects.registry import SubjectConfig

# Turning an upright page clockwise by the key makes it look like the value.
APPEARS_AFTER_TURN = {
    0: "upright",
    90: "rotated_clockwise",
    180: "upside_down",
    270: "rotated_counterclockwise",
}


@dataclass(frozen=True)
class OrientationCase:
    page: str
    subject: str
    turned: int
    expected: str
    judged: str | None
    confidence: float | None
    seconds: float
    threshold: float
    error: str | None = None

    @property
    def would_turn(self) -> bool:
        return (
            self.judged is not None
            and self.judged != "upright"
            and (self.confidence or 0.0) >= self.threshold
        )

    @property
    def outcome(self) -> str:
        if self.would_turn:
            return "fixed" if self.judged == self.expected else "wrong"
        return "left" if self.expected == "upright" else "missed"


@dataclass
class OrientationSummary:
    threshold: float
    cases: list[OrientationCase] = field(default_factory=list)

    def count(self, outcome: str) -> int:
        return sum(1 for c in self.cases if c.outcome == outcome)

    @property
    def judged_right(self) -> int:
        """Judgement equal to the truth, whatever the confidence."""
        return sum(1 for c in self.cases if c.judged == c.expected)

    @property
    def seconds_per_call(self) -> float:
        return sum(c.seconds for c in self.cases) / len(self.cases) if self.cases else 0.0

    def as_json(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "calls": len(self.cases),
            "fixed": self.count("fixed"),
            "left": self.count("left"),
            "wrong": self.count("wrong"),
            "missed": self.count("missed"),
            "judged_right": self.judged_right,
            "no_valid_reply": sum(1 for c in self.cases if c.judged is None),
            "timeouts": sum(1 for c in self.cases if c.error == "timeout"),
            "server_errors": sum(1 for c in self.cases if c.error == "server_error"),
            "seconds_per_call": round(self.seconds_per_call, 2),
            "cases": [
                {
                    "page": c.page,
                    "subject": c.subject,
                    "turned": c.turned,
                    "expected": c.expected,
                    "judged": c.judged,
                    "confidence": c.confidence,
                    "outcome": c.outcome,
                    "error": c.error,
                    "seconds": round(c.seconds, 2),
                }
                for c in self.cases
            ],
        }


@dataclass(frozen=True)
class OrientationPage:
    path: Path
    subject: str
    # How the stored image looks: "upright" for the labelled set.
    appears: str = "upright"


def evaluate_orientation(
    reader: Reader,
    pages: list[OrientationPage],
    subject_config: Callable[[str], SubjectConfig],
    *,
    turns: tuple[int, ...],
    threshold: float,
    progress: Callable[[str], None] | None = None,
    cache: EvalCache | None = None,
    cache_prefix: str = "",
) -> OrientationSummary:
    summary = OrientationSummary(threshold)
    for page in pages:
        # Extra pages are used as they are; labelled upright pages are also turned.
        page_turns = turns if page.appears == "upright" else (0,)
        for turned in page_turns:
            expected = _appearance(page.appears, turned)
            key = f"orient|{cache_prefix}|{page.subject}/{page.path.as_posix()}|{turned}"
            cached = cache.get(key) if cache is not None else None
            note = " (cached)"
            if cached is None:
                started = time.monotonic()
                judged: str | None = None
                confidence: float | None = None
                error: str | None = None
                try:
                    result = reader.transcribe(
                        [PageImage(0, page.path, None, rotation=turned)],
                        subject_config(page.subject),
                    )
                    judged = result.pages[0].orientation
                    confidence = result.pages[0].orientation_confidence
                except ModelOutputInvalidError as exc:
                    error = str(exc)
                except ModelUnavailableError as exc:
                    # A reply that never finishes (seen on upside-down pages: the model rambles
                    # until the call times out) is a result to report, not a reason to stop.
                    # An Ollama 5xx mid-reply was seen on a turned page (2026-10-15). A server that
                    # cannot be reached still stops the run. (Slow replies arrive as
                    # ModelCallTimeoutError, an invalid output with the message "timeout".)
                    if not str(exc).startswith("http_5"):
                        raise
                    error = "server_error"
                cached = {
                    "judged": judged,
                    "confidence": confidence,
                    "error": error,
                    "seconds": time.monotonic() - started,
                }
                if cache is not None:
                    cache.put(key, cached)
                note = ""
            case = OrientationCase(
                page=f"{page.path.parent.name}/{page.path.name}",
                subject=page.subject,
                turned=turned,
                expected=expected,
                judged=cached["judged"],
                confidence=cached["confidence"],
                seconds=float(cached["seconds"]),
                threshold=threshold,
                error=cached.get("error"),
            )
            summary.cases.append(case)
            if progress:
                progress(
                    f"  orientation {page.subject}/{case.page} turned {turned}: "
                    f"{case.judged} ({case.confidence}) -> {case.outcome}, "
                    f"{case.seconds:.1f}s{note}"
                )
    return summary


def _appearance(appears: str, turned: int) -> str:
    """How a page that looks like ``appears`` looks after a further clockwise turn."""
    # ORIENTATION_TURN gives the clockwise turn that makes each appearance upright, so the page
    # is (360 - fix) degrees clockwise from upright.
    offset = (360 - ORIENTATION_TURN[appears]) % 360
    return APPEARS_AFTER_TURN[(offset + turned) % 360]
