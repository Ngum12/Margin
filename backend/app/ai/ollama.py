"""Reader and Marker backed by a local Ollama server."""

import io
import logging

from PIL import Image

from app.ai.ollama_client import OllamaClient
from app.ai.prompts import load_prompt
from app.ai.types import (
    ExamSpec,
    MarkingProposal,
    ModelInfo,
    ModelOutputInvalidError,
    ModelUnavailableError,
    PageImage,
    PageText,
    PointProposal,
    QuestionProposal,
    QuestionSpec,
    Transcription,
)
from app.ai.validation import (
    MARKER_SCHEMA,
    READER_SCHEMA,
    parse_marker_output,
    parse_reader_output,
)
from app.clock import utcnow
from app.subjects.registry import SubjectConfig

logger = logging.getLogger(__name__)


def resolve_model(client: OllamaClient, name: str) -> ModelInfo:
    """Look up the installed model's digest; it is stored as the model version."""
    models = client.list_models()
    digest = models.get(name) or models.get(f"{name}:latest")
    if digest is None:
        # A configuration problem (model not pulled yet): retried later, shown in the AI status.
        raise ModelUnavailableError(f"model_not_installed:{name}")
    return ModelInfo(name, digest[:12], "ollama")


def _jpeg_for_model(path: str, max_px: int) -> bytes:
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_px, max_px))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=90)
        return buffer.getvalue()


class OllamaReader:
    def __init__(
        self, client: OllamaClient, model: ModelInfo, *, max_image_px: int, output_retries: int
    ) -> None:
        self._client = client
        self.model = model
        self._max_px = max_image_px
        self._retries = output_retries
        self._prompt = load_prompt("reader")
        self.prompt_version = self._prompt.version

    def transcribe(self, pages: list[PageImage], subject: SubjectConfig) -> Transcription:
        hints = "".join(f"  - {hint}\n" for hint in subject.reader.notation_hints)
        prompt = self._prompt.render(
            subject_hints=f"- Subject notes ({subject.names.en}):\n{hints}" if hints else ""
        )
        texts = []
        for page in pages:
            image = _jpeg_for_model(str(page.path), self._max_px)
            texts.append(PageText(page.page_id, self._ask(prompt, image)))
        return Transcription(texts, self.model, self.prompt_version, utcnow())

    def _ask(self, prompt: str, image: bytes) -> str:
        error = ModelOutputInvalidError("no_attempt")
        for _ in range(self._retries + 1):
            raw = self._client.chat_json(self.model.name, prompt, READER_SCHEMA, images=[image])
            try:
                return parse_reader_output(raw)
            except ModelOutputInvalidError as exc:
                logger.warning("Reader output invalid (%s)", exc)
                error = exc
        raise error


class OllamaMarker:
    def __init__(self, client: OllamaClient, model: ModelInfo, *, output_retries: int) -> None:
        self._client = client
        self.model = model
        self._retries = output_retries
        self._prompt = load_prompt("marker")
        self.prompt_version = self._prompt.version

    def mark(self, transcription: Transcription, exam: ExamSpec) -> MarkingProposal:
        answer = transcription.full_text
        questions = []
        failed = []
        for question in exam.questions:
            try:
                points = self._mark_question(question, answer, exam.subject.names.en)
                questions.append(QuestionProposal(question.id, points))
            except ModelOutputInvalidError as exc:
                logger.warning("Marker output invalid for question %s (%s)", question.label, exc)
                failed.append(question.id)
        return MarkingProposal(
            tuple(questions), self.model, self.prompt_version, utcnow(), tuple(failed)
        )

    def _mark_question(
        self, question: QuestionSpec, answer: str, subject: str
    ) -> tuple[PointProposal, ...]:
        points = "\n".join(
            f"- point_id {p.id} ({p.marks} mark{'s' if p.marks != 1 else ''}): {p.description}"
            + (f" | also accept: {'; '.join(p.alternatives)}" if p.alternatives else "")
            for p in question.points
        )
        prompt = self._prompt.render(
            subject=subject,
            label=question.label,
            max_marks=str(question.max_marks),
            question=question.prompt_text or "(see mark scheme)",
            points=points,
            answer=answer,
        )
        error = ModelOutputInvalidError("no_attempt")
        for _ in range(self._retries + 1):
            raw = self._client.chat_json(self.model.name, prompt, MARKER_SCHEMA)
            try:
                return parse_marker_output(raw, question, answer)
            except ModelOutputInvalidError as exc:
                error = exc
        raise error
