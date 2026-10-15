"""Measure a Reader against typed ground truth (owner requirement, Phase 3).

Two folder layouts are accepted under ``<root>/<subject_code>/``:

- one folder per script: ``<student>/page1.jpg, page2.jpg, ...`` with ``<student>/truth.txt``
  holding the whole script's exact transcription (pages in order);
- one file pair per page: ``<name>.jpg|.png`` with ``<name>.txt``.

Metrics, micro-averaged over all scripts of a subject (summed errors / summed reference length):
- CER: character edit distance / reference characters.
- WER: word edit distance / reference words (words split on whitespace).
- Key-token recall: share of the reference's numbers, formulae and operators that also appear in
  the transcription (counted as multisets).
- Invalid outputs: pages where the Reader's reply failed validation after its retries.

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

from app.ai.eval_cache import EvalCache
from app.ai.types import ModelOutputInvalidError, PageImage, Reader
from app.subjects.registry import SubjectConfig

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")
TRUTH_NAME = "truth.txt"

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


@dataclass(frozen=True)
class EvalScript:
    subject: str
    name: str  # student folder, or page file stem in the one-pair-per-page layout
    images: tuple[Path, ...]
    truth: Path


def _natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name)]


def find_scripts(root: Path, subject: str | None = None) -> dict[str, list[EvalScript]]:
    """Map subject code -> scripts that have both images and ground truth."""
    found: dict[str, list[EvalScript]] = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if subject and folder.name != subject:
            continue
        scripts: list[EvalScript] = []
        for student in sorted((p for p in folder.iterdir() if p.is_dir()), key=_natural_key):
            images = sorted(
                (p for p in student.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES),
                key=_natural_key,
            )
            truth = student / TRUTH_NAME
            if images and truth.is_file():
                scripts.append(EvalScript(folder.name, student.name, tuple(images), truth))
        for image in sorted(folder.iterdir(), key=_natural_key):
            pair = image.with_suffix(".txt")
            if image.suffix.lower() in IMAGE_SUFFIXES and pair.is_file():
                scripts.append(EvalScript(folder.name, image.stem, (image,), pair))
        if scripts:
            found[folder.name] = scripts
    return found


@dataclass
class ScriptResult:
    script: EvalScript
    transcription: str
    page_seconds: list[float]
    invalid_pages: int
    score: Score


@dataclass
class SubjectReport:
    subject: str
    scripts: list[ScriptResult] = field(default_factory=list)

    @property
    def total(self) -> Score:
        total = Score()
        for result in self.scripts:
            total.add(result.score)
        return total

    @property
    def pages(self) -> int:
        return sum(len(r.page_seconds) for r in self.scripts)

    @property
    def seconds_per_page(self) -> float:
        seconds = [s for r in self.scripts for s in r.page_seconds]
        return sum(seconds) / len(seconds) if seconds else 0.0

    @property
    def invalid_pages(self) -> int:
        return sum(r.invalid_pages for r in self.scripts)


def evaluate(
    reader: Reader,
    scripts: dict[str, list[EvalScript]],
    subject_config: Callable[[str], SubjectConfig],
    progress: Callable[[str], None] | None = None,
    cache: EvalCache | None = None,
    cache_prefix: str = "",
) -> list[SubjectReport]:
    reports = []
    for subject, items in scripts.items():
        config = subject_config(subject)
        report = SubjectReport(subject)
        for script in items:
            texts: list[str] = []
            seconds: list[float] = []
            invalid = 0
            for index, image in enumerate(script.images):
                key = f"read|{cache_prefix}|{subject}/{script.name}/{image.name}"
                cached = cache.get(key) if cache is not None else None
                note = " (cached)"
                if cached is None:
                    started = time.monotonic()
                    text: str | None
                    try:
                        # sidecar_text is deliberately None: the Reader never sees the ground truth.
                        result = reader.transcribe([PageImage(index, image, None)], config)
                        text = result.pages[0].text
                    except ModelOutputInvalidError:
                        text = None
                    cached = {"text": text, "seconds": time.monotonic() - started}
                    if cache is not None:
                        cache.put(key, cached)
                    note = ""
                if cached["text"] is None:
                    invalid += 1
                else:
                    texts.append(cached["text"])
                seconds.append(cached["seconds"])
                if progress:
                    progress(
                        f"  read {subject}/{script.name}/{image.name}: {seconds[-1]:.1f}s{note}"
                    )
            transcription = "\n".join(texts)
            report.scripts.append(
                ScriptResult(
                    script,
                    transcription,
                    seconds,
                    invalid,
                    score(script.truth.read_text("utf-8"), transcription),
                )
            )
        reports.append(report)
    return reports
