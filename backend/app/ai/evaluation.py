"""Measure a Reader against typed ground truth (owner requirement, Phase 3).

Folder layout::

    <root>/<subject_code>/<name>.jpg|.jpeg|.png   page image
    <root>/<subject_code>/<name>.txt              exact typed transcription (agreed notation)

Metrics, micro-averaged over all pages of a subject (summed errors / summed reference length):
- CER: character edit distance / reference characters.
- WER: word edit distance / reference words (words split on whitespace).
- Key-token recall: share of the reference's numbers, formulae and operators that also appear in
  the transcription (counted as multisets).

Text is compared as written: case, spelling and punctuation matter (the Reader must keep the
student's errors). Only line endings and trailing spaces are normalised. The ground truth is
never shown to the Reader being evaluated.
"""

import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.ai.types import ModelOutputInvalidError, PageImage, Reader
from app.subjects.registry import SubjectConfig

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")

# Formulae and notation (H_2O, x^2, Na^+, CO_2, H_2SO_4), then numbers, then operators.
_KEY_TOKEN = re.compile(
    r"(?P<formula>[A-Za-z(][A-Za-z0-9()]*(?:[_^][A-Za-z0-9+\-()]+)+)"
    r"|(?P<number>\d+(?:[.,]\d+)?(?:/\d+)?)"
    r"|(?P<operator><=>|->|<=|>=|[=+×÷*/√<>^]|(?<![A-Za-z])-(?![A-Za-z]))"  # noqa: RUF001 - real multiplication and division signs
)


def normalise(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    """Levenshtein distance (insertions, deletions, substitutions all cost 1)."""
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, start=1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ref_item != hyp_item))
            )
        previous = current
    return previous[-1]


def key_tokens(text: str) -> list[str]:
    return [m.group(0) for m in _KEY_TOKEN.finditer(text)]


@dataclass
class Score:
    char_edits: int = 0
    char_total: int = 0
    word_edits: int = 0
    word_total: int = 0
    key_found: int = 0
    key_total: int = 0

    def add(self, other: "Score") -> None:
        for name in vars(self):
            setattr(self, name, getattr(self, name) + getattr(other, name))

    @property
    def cer(self) -> float:
        return self.char_edits / self.char_total if self.char_total else 0.0

    @property
    def wer(self) -> float:
        return self.word_edits / self.word_total if self.word_total else 0.0

    @property
    def key_token_recall(self) -> float:
        return self.key_found / self.key_total if self.key_total else 1.0


def score(reference: str, hypothesis: str) -> Score:
    ref, hyp = normalise(reference), normalise(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    ref_keys, hyp_keys = Counter(key_tokens(ref)), Counter(key_tokens(hyp))
    return Score(
        char_edits=edit_distance(ref, hyp),
        char_total=len(ref),
        word_edits=edit_distance(ref_words, hyp_words),
        word_total=len(ref_words),
        key_found=sum((ref_keys & hyp_keys).values()),
        key_total=sum(ref_keys.values()),
    )


@dataclass
class PageResult:
    subject: str
    name: str
    seconds: float
    valid_output: bool
    score: Score


@dataclass
class SubjectReport:
    subject: str
    pages: list[PageResult] = field(default_factory=list)

    @property
    def total(self) -> Score:
        total = Score()
        for page in self.pages:
            total.add(page.score)
        return total

    @property
    def seconds_per_page(self) -> float:
        return sum(p.seconds for p in self.pages) / len(self.pages) if self.pages else 0.0

    @property
    def invalid_outputs(self) -> int:
        return sum(1 for p in self.pages if not p.valid_output)


def find_pages(root: Path, subject: str | None = None) -> dict[str, list[tuple[Path, Path]]]:
    """Map subject code -> [(image, ground truth)], skipping images without ground truth."""
    found: dict[str, list[tuple[Path, Path]]] = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if subject and folder.name != subject:
            continue
        pairs = [
            (image, image.with_suffix(".txt"))
            for image in sorted(folder.iterdir())
            if image.suffix.lower() in IMAGE_SUFFIXES and image.with_suffix(".txt").is_file()
        ]
        if pairs:
            found[folder.name] = pairs
    return found


def evaluate(
    reader: Reader,
    pages: dict[str, list[tuple[Path, Path]]],
    subject_config: Callable[[str], SubjectConfig],
    progress: Callable[[str], None] | None = None,
) -> list[SubjectReport]:
    reports = []
    for subject, pairs in pages.items():
        config = subject_config(subject)
        report = SubjectReport(subject)
        for index, (image, truth) in enumerate(pairs):
            started = time.monotonic()
            try:
                # sidecar_text is deliberately None: the Reader never sees the ground truth.
                result = reader.transcribe([PageImage(index, image, None)], config)
                text, valid = result.pages[0].text, True
            except ModelOutputInvalidError:
                text, valid = "", False
            seconds = time.monotonic() - started
            report.pages.append(
                PageResult(
                    subject, image.name, seconds, valid, score(truth.read_text("utf-8"), text)
                )
            )
            if progress:
                progress(f"{subject}/{image.name}: {seconds:.1f}s")
        reports.append(report)
    return reports
