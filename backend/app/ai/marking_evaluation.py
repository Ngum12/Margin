"""Compare the Marker's proposed marks with a teacher's expected marks, per question.

Inputs:
- the mark scheme CSV for each subject (the same format as the exam setup import);
- an expected-marks CSV with columns ``subject, student, question, expected_marks, category``
  (other columns are ignored), one row per question per student.

A question's proposed mark is the sum of its points' proposed marks, capped at the question's
maximum (the cap a teacher applies for "any N of M" questions). Questions whose marker output
stayed invalid after retries count as disagreements and are reported as failed.

Results are also given separately for questions whose expected category is
``language_expression`` (the idea is right, the English is weak): the system must not take marks
off for weak English.
"""

import csv
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai.eval_cache import EvalCache, text_hash
from app.ai.types import (
    ExamSpec,
    Marker,
    ModelInfo,
    PageText,
    PointSpec,
    QuestionSpec,
    Transcription,
)
from app.clock import utcnow
from app.db.models import ErrorCategory
from app.services.mark_scheme_import import decode_csv, parse_mark_scheme_csv
from app.subjects.registry import SubjectConfig

LANGUAGE = "language_expression"


def exam_spec_from_csv(path: Path, subject: SubjectConfig) -> ExamSpec:
    text = decode_csv(path.read_bytes())
    if not isinstance(text, str):
        raise ValueError(f"{path}: {text.code}")
    result = parse_mark_scheme_csv(text)
    if result.scheme is None:
        raise ValueError(f"{path}: {[i.code for i in result.issues]}")
    return ExamSpec(
        subject=subject,
        questions=tuple(
            QuestionSpec(
                id=qi + 1,
                label=q.label,
                prompt_text=q.prompt_text,
                max_marks=q.max_marks,
                points=tuple(
                    PointSpec(100 * (qi + 1) + pi, p.description, p.marks, tuple(p.alternatives))
                    for pi, p in enumerate(q.points)
                ),
            )
            for qi, q in enumerate(result.scheme.questions)
        ),
    )


def find_mark_scheme(folder: Path, subject: str) -> Path:
    matches = sorted(p for p in folder.glob("*.csv") if subject in p.stem.lower())
    if len(matches) != 1:
        raise ValueError(
            f"Expected one mark scheme CSV for {subject} in {folder}, found {len(matches)}"
        )
    return matches[0]


@dataclass(frozen=True)
class Expected:
    marks: int
    category: str


def load_expected(path: Path) -> dict[tuple[str, str, str], Expected]:
    rows: dict[tuple[str, str, str], Expected] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                row["subject"].strip(),
                row["student"].strip(),
                row["question"].strip().casefold(),
            )
            rows[key] = Expected(int(row["expected_marks"]), row["category"].strip())
    return rows


@dataclass(frozen=True)
class QuestionComparison:
    subject: str
    student: str
    question: str
    expected: int
    expected_category: str
    proposed: int | None  # None: the marker failed on this question
    proposed_categories: tuple[str, ...] = ()


def compare_script(
    marker: Marker,
    spec: ExamSpec,
    subject: str,
    student: str,
    answer: str,
    expected: dict[tuple[str, str, str], Expected],
) -> tuple[list[QuestionComparison], float]:
    """Mark one script and compare per question. Returns comparisons and seconds taken."""
    transcription = Transcription(
        [PageText(0, answer)], ModelInfo("evaluation", "-", "input"), "-", utcnow()
    )
    started = time.monotonic()
    proposal = marker.mark(transcription, spec)
    seconds = time.monotonic() - started
    by_question = {q.question_id: q for q in proposal.questions}
    comparisons = []
    for question in spec.questions:
        want = expected.get((subject, student, question.label.casefold()))
        if want is None:
            continue  # no expected mark for this question: not scored
        got = by_question.get(question.id)
        proposed = (
            min(sum(p.awarded_marks for p in got.points), question.max_marks) if got else None
        )
        categories = tuple(p.error_category.value for p in got.points) if got else ()
        comparisons.append(
            QuestionComparison(
                subject, student, question.label, want.marks, want.category, proposed, categories
            )
        )
    return comparisons, seconds


@dataclass
class MarkingSummary:
    comparisons: list[QuestionComparison] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)

    def _subset(self, language_only: bool) -> list[QuestionComparison]:
        return [c for c in self.comparisons if not language_only or c.expected_category == LANGUAGE]

    def questions(self, language_only: bool = False) -> int:
        return len(self._subset(language_only))

    def failed(self, language_only: bool = False) -> int:
        return sum(1 for c in self._subset(language_only) if c.proposed is None)

    def exact_agreement(self, language_only: bool = False) -> float:
        items = self._subset(language_only)
        return sum(1 for c in items if c.proposed == c.expected) / len(items) if items else 0.0

    def mean_absolute_difference(self, language_only: bool = False) -> float:
        """Over questions the marker answered (failed ones are counted in ``failed``)."""
        answered = [c for c in self._subset(language_only) if c.proposed is not None]
        if not answered:
            return 0.0
        return sum(abs(c.expected - (c.proposed or 0)) for c in answered) / len(answered)

    def marks_lost(self, language_only: bool = True) -> int:
        """Marks the AI proposed below the expected mark (answered questions only)."""
        return sum(
            max(0, c.expected - c.proposed)
            for c in self._subset(language_only)
            if c.proposed is not None
        )

    def language_called_conceptual(self) -> int:
        """Language-expression questions where any point was labelled a conceptual error."""
        return sum(
            1
            for c in self._subset(True)
            if ErrorCategory.CONCEPTUAL_ERROR.value in c.proposed_categories
        )

    @property
    def seconds_per_script(self) -> float:
        return sum(self.seconds) / len(self.seconds) if self.seconds else 0.0


def evaluate_marking(
    marker: Marker,
    scripts: list[tuple[str, str, str]],
    specs: dict[str, ExamSpec],
    expected: dict[tuple[str, str, str], Expected],
    progress: Callable[[str], None] | None = None,
    cache: EvalCache | None = None,
    cache_prefix: str = "",
) -> MarkingSummary:
    """``scripts``: (subject, student, answer text) to mark."""
    summary = MarkingSummary()
    for subject, student, answer in scripts:
        key = f"mark|{cache_prefix}|{subject}/{student}|{text_hash(answer)}"
        cached = cache.get(key) if cache else None
        note = " (cached)"
        if cached is None:
            comparisons, seconds = compare_script(
                marker, specs[subject], subject, student, answer, expected
            )
            cached = {"comparisons": [_to_json(c) for c in comparisons], "seconds": seconds}
            if cache:
                cache.put(key, cached)
            note = ""
        summary.comparisons.extend(_from_json(c) for c in cached["comparisons"])
        summary.seconds.append(cached["seconds"])
        if progress:
            progress(f"  marked {subject}/{student}: {cached['seconds']:.1f}s{note}")
    return summary


def _to_json(c: QuestionComparison) -> dict[str, Any]:
    return {**vars(c), "proposed_categories": list(c.proposed_categories)}


def _from_json(data: dict[str, Any]) -> QuestionComparison:
    return QuestionComparison(**{**data, "proposed_categories": tuple(data["proposed_categories"])})
