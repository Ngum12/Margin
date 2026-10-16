"""Reader and Marker backed by a local Ollama server."""

import io
import logging
from collections.abc import Callable
from typing import Literal

from PIL import Image

from app.ai.ollama_client import OllamaClient
from app.ai.prompts import load_prompt
from app.ai.types import (
    ExamSpec,
    MarkingProposal,
    ModelCallTimeoutError,
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
    READER_SCHEMA,
    ReaderOutput,
    answer_lines,
    marker_schema_for,
    numbered_answer,
    parse_marker_lines_output,
    parse_marker_output,
    parse_reader_output,
    point_key,
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


# A call that times out is retried once only, whatever MARGIN_MODEL_OUTPUT_RETRIES says: each
# try can take the whole time limit (owner, 2026-10-15).
TIMEOUT_RETRIES = 1


def call_with_retries[T](call: Callable[[], T], output_retries: int, what: str) -> T:
    """Run one model call, retrying invalid output up to ``output_retries`` times and a
    time-out once. The last error is raised when the retries are used up."""
    invalid = timeouts = 0
    while True:
        try:
            return call()
        except ModelCallTimeoutError:
            timeouts += 1
            if timeouts > TIMEOUT_RETRIES:
                raise
            logger.warning("%s call timed out; trying once more", what)
        except ModelOutputInvalidError as exc:
            invalid += 1
            if invalid > output_retries:
                raise
            logger.warning("%s output invalid (%s)", what, exc)


def reply_example(question: QuestionSpec, evidence: Literal["quote", "lines"]) -> str:
    """The JSON shape the marker must reply with, listing this question's point keys."""
    field = (
        '"evidence_lines": [<line numbers>]'
        if evidence == "lines"
        else '"evidence": "<exact quote or empty>"'
    )
    entries = ",\n  ".join(
        f'"{point_key(p.id)}": {{"awarded_marks": <0 to {p.marks}>, {field}, '
        '"confidence": <0 to 1>, "error_category": "<category>"}'
        for p in question.points
    )
    return '{"points": {\n  ' + entries + "\n}}"


def _jpeg_for_model(path: str, max_px: int, rotation: int = 0) -> bytes:
    with Image.open(path) as source:
        image = source.convert("RGB")
        if rotation % 360:
            # PIL turns anticlockwise; page rotations are clockwise degrees.
            image = image.rotate(-(rotation % 360), expand=True)
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
            image = _jpeg_for_model(str(page.path), self._max_px, page.rotation)
            out = self._ask(prompt, image)
            texts.append(
                PageText(page.page_id, out.text, out.orientation, out.orientation_confidence)
            )
        return Transcription(texts, self.model, self.prompt_version, utcnow())

    def _ask(self, prompt: str, image: bytes) -> ReaderOutput:
        def call() -> ReaderOutput:
            raw = self._client.chat_json(self.model.name, prompt, READER_SCHEMA, images=[image])
            return parse_reader_output(raw)

        return call_with_retries(call, self._retries, "Reader")


class OllamaMarker:
    def __init__(
        self,
        client: OllamaClient,
        model: ModelInfo,
        *,
        output_retries: int,
        evidence: Literal["quote", "lines"] = "quote",
    ) -> None:
        self._client = client
        self.model = model
        self._retries = output_retries
        self._evidence = evidence
        self._prompt = load_prompt("marker_lines" if evidence == "lines" else "marker")
        self.prompt_version = self._prompt.version

    on_question: Callable[[int, int], None] | None = None

    def mark(self, transcription: Transcription, exam: ExamSpec) -> MarkingProposal:
        answer = transcription.full_text
        questions = []
        failed = []
        for number, question in enumerate(exam.questions, start=1):
            if self.on_question is not None:
                self.on_question(number, len(exam.questions))
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
            f"- {point_key(p.id)} ({p.marks} mark{'s' if p.marks != 1 else ''}): {p.description}"
            + (f" | also accept: {'; '.join(p.alternatives)}" if p.alternatives else "")
            + f" | examiner rules: {p.rules.model_dump_json()}"
            for p in question.points
        )
        lines = answer_lines(answer)
        prompt = self._prompt.render(
            subject=subject,
            label=question.label,
            max_marks=str(question.max_marks),
            question=question.prompt_text or "(see mark scheme)",
            points=points,
            answer=numbered_answer(lines) if self._evidence == "lines" else answer,
            reply=reply_example(question, self._evidence),
        )
        # Per-question schema (owner, 2026-10-15): exactly this question's points, each once.
        schema = marker_schema_for(question, len(lines) if self._evidence == "lines" else None)

        def call() -> tuple[PointProposal, ...]:
            raw = self._client.chat_json(self.model.name, prompt, schema)
            if self._evidence == "lines":
                return parse_marker_lines_output(raw, question, lines)
            return parse_marker_output(raw, question, answer)

        return call_with_retries(call, self._retries, "Marker")
