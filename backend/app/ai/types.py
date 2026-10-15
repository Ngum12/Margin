"""The model layer's contract. The rest of the application depends only on these types and on
the Reader and Marker interfaces, never on a particular model (brief section 5)."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.db.models import ErrorCategory
from app.subjects.registry import SubjectConfig


class ModelUnavailableError(Exception):
    """The model server could not be reached or timed out. The job is retried later."""


class ModelOutputInvalidError(Exception):
    """The model replied, but its output failed validation (after the allowed retries)."""


@dataclass(frozen=True)
class ModelInfo:
    name: str
    version: str  # Ollama digest (shortened) or "mock-1"
    source: str  # "ollama" or "mock"


@dataclass(frozen=True)
class PageImage:
    page_id: int
    path: Path
    # Optional typed ground truth next to the image (used by MockReader for demos/evaluation).
    sidecar_text: Path | None = None
    # Clockwise degrees to turn the stored image before reading it (the page's orientation).
    rotation: int = 0


@dataclass(frozen=True)
class PageText:
    page_id: int
    text: str
    # The Reader's judgement of which way up the page was as sent (None when not given).
    orientation: str | None = None
    orientation_confidence: float | None = None


@dataclass(frozen=True)
class Transcription:
    pages: list[PageText]
    model: ModelInfo
    prompt_version: str
    created_at: datetime

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


@dataclass(frozen=True)
class PointSpec:
    id: int
    description: str
    marks: int  # whole marks (D-018)
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionSpec:
    id: int
    label: str
    prompt_text: str
    max_marks: int
    points: tuple[PointSpec, ...]


@dataclass(frozen=True)
class ExamSpec:
    subject: SubjectConfig
    questions: tuple[QuestionSpec, ...]


@dataclass(frozen=True)
class PointProposal:
    point_id: int
    awarded_marks: int
    evidence: str
    confidence: float
    error_category: ErrorCategory


@dataclass(frozen=True)
class QuestionProposal:
    question_id: int
    points: tuple[PointProposal, ...]


@dataclass(frozen=True)
class MarkingProposal:
    questions: tuple[QuestionProposal, ...]
    model: ModelInfo
    prompt_version: str
    created_at: datetime
    # Questions whose output stayed invalid after retries: nothing is proposed for them.
    failed_question_ids: tuple[int, ...] = field(default_factory=tuple)


class Reader(Protocol):
    @property
    def model(self) -> ModelInfo: ...

    @property
    def prompt_version(self) -> str: ...

    def transcribe(self, pages: list[PageImage], subject: SubjectConfig) -> Transcription: ...


class Marker(Protocol):
    @property
    def model(self) -> ModelInfo: ...

    @property
    def prompt_version(self) -> str: ...

    def mark(self, transcription: Transcription, exam: ExamSpec) -> MarkingProposal: ...
