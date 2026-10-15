"""Strict validation of model output. Anything that does not pass is rejected, never repaired.

The JSON schemas here are also sent to Ollama as the ``format`` constraint, so the model is asked
for exactly the shape we accept.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from app.ai.types import ModelOutputInvalidError, PointProposal, QuestionSpec
from app.db.models import ErrorCategory

ORIENTATIONS = ("upright", "upside_down", "rotated_clockwise", "rotated_counterclockwise")
# Clockwise degrees that turn a page the Reader judged this way back upright.
ORIENTATION_TURN = {
    "upright": 0,
    "upside_down": 180,
    "rotated_clockwise": 270,
    "rotated_counterclockwise": 90,
}

READER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "orientation": {"type": "string", "enum": list(ORIENTATIONS)},
        "orientation_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["text", "orientation", "orientation_confidence"],
    "additionalProperties": False,
}

MARKER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point_id": {"type": "integer"},
                    "awarded_marks": {"type": "integer", "minimum": 0},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "error_category": {"type": "string", "enum": [c.value for c in ErrorCategory]},
                },
                "required": [
                    "point_id",
                    "awarded_marks",
                    "evidence",
                    "confidence",
                    "error_category",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["points"],
    "additionalProperties": False,
}


class _Closed(BaseModel):
    # No extra keys; numbers and text must arrive as such ("2" or 2.0 is not a whole number).
    model_config = ConfigDict(extra="forbid")


class _ReaderOut(_Closed):
    text: StrictStr


class _PointOut(_Closed):
    point_id: StrictInt
    awarded_marks: StrictInt = Field(ge=0)
    evidence: StrictStr
    confidence: float = Field(ge=0, le=1)
    error_category: ErrorCategory


class _MarkerOut(_Closed):
    points: list[_PointOut]


def _load_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelOutputInvalidError("not_json") from exc


_ORIENTATION_KEYS = ("orientation", "orientation_confidence")


@dataclass(frozen=True)
class ReaderOutput:
    text: str
    # None when the orientation judgement is missing or invalid: then nothing is rotated.
    orientation: str | None = None
    orientation_confidence: float | None = None


def parse_reader_output(raw: str) -> ReaderOutput:
    """The transcription must be valid; the orientation judgement is optional (owner change 1:
    an invalid judgement keeps the read and rotates nothing)."""
    data = _load_json(raw)
    if not isinstance(data, dict) or not set(data) <= {"text", *_ORIENTATION_KEYS}:
        raise ModelOutputInvalidError("reader_schema")
    try:
        text = _ReaderOut.model_validate({"text": data.get("text")}).text
    except ValidationError as exc:
        raise ModelOutputInvalidError("reader_schema") from exc
    orientation = data.get("orientation")
    confidence = data.get("orientation_confidence")
    if (
        orientation not in ORIENTATIONS
        or isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not 0 <= confidence <= 1
    ):
        return ReaderOutput(text)
    return ReaderOutput(text, str(orientation), float(confidence))


_SPACES = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _SPACES.sub(" ", text).strip().casefold()


def evidence_is_quoted(evidence: str, answer: str) -> bool:
    """Evidence must be a verbatim quote (whitespace and letter case aside)."""
    return _normalise(evidence) in _normalise(answer)


def parse_marker_output(raw: str, question: QuestionSpec, answer: str) -> tuple[PointProposal, ...]:
    """Validate the marker's output for one question against its mark scheme and the answer."""
    try:
        parsed = _MarkerOut.model_validate(_load_json(raw))
    except ValidationError as exc:
        raise ModelOutputInvalidError("marker_schema") from exc

    expected = {p.id: p for p in question.points}
    seen = [p.point_id for p in parsed.points]
    if sorted(seen) != sorted(expected):
        raise ModelOutputInvalidError("marker_points_mismatch")

    proposals = []
    for point in parsed.points:
        spec = expected[point.point_id]
        if point.awarded_marks > spec.marks:
            raise ModelOutputInvalidError("marker_marks_out_of_range")
        evidence = point.evidence.strip()
        if point.awarded_marks > 0 and not evidence:
            raise ModelOutputInvalidError("marker_missing_evidence")
        if evidence and not evidence_is_quoted(evidence, answer):
            raise ModelOutputInvalidError("marker_invented_evidence")
        proposals.append(
            PointProposal(
                point_id=point.point_id,
                awarded_marks=point.awarded_marks,
                evidence=evidence,
                confidence=point.confidence,
                error_category=point.error_category,
            )
        )
    order = {p.id: i for i, p in enumerate(question.points)}
    return tuple(sorted(proposals, key=lambda p: order[p.point_id]))


MAX_EVIDENCE_LINES = 6

MARKER_LINES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point_id": {"type": "integer"},
                    "awarded_marks": {"type": "integer", "minimum": 0},
                    "evidence_lines": {"type": "array", "items": {"type": "integer"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "error_category": {"type": "string", "enum": [c.value for c in ErrorCategory]},
                },
                "required": [
                    "point_id",
                    "awarded_marks",
                    "evidence_lines",
                    "confidence",
                    "error_category",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["points"],
    "additionalProperties": False,
}


class _LinePointOut(_Closed):
    point_id: StrictInt
    awarded_marks: StrictInt = Field(ge=0)
    evidence_lines: list[StrictInt]
    confidence: float = Field(ge=0, le=1)
    error_category: ErrorCategory


class _MarkerLinesOut(_Closed):
    points: list[_LinePointOut]


def answer_lines(answer: str) -> list[str]:
    return answer.replace("\r\n", "\n").split("\n")


def numbered_answer(lines: list[str]) -> str:
    return "\n".join(f"L{i}: {line}" for i, line in enumerate(lines, start=1))


def parse_marker_lines_output(
    raw: str, question: QuestionSpec, lines: list[str]
) -> tuple[PointProposal, ...]:
    """Validate line-number evidence (D-047). Margin copies the cited lines itself, so the
    evidence is always the student's own words."""
    try:
        parsed = _MarkerLinesOut.model_validate(_load_json(raw))
    except ValidationError as exc:
        raise ModelOutputInvalidError("marker_schema") from exc

    expected = {p.id: p for p in question.points}
    if sorted(p.point_id for p in parsed.points) != sorted(expected):
        raise ModelOutputInvalidError("marker_points_mismatch")

    proposals = []
    for point in parsed.points:
        spec = expected[point.point_id]
        if point.awarded_marks > spec.marks:
            raise ModelOutputInvalidError("marker_marks_out_of_range")
        cited = sorted(set(point.evidence_lines))
        if any(n < 1 or n > len(lines) for n in cited):
            raise ModelOutputInvalidError("marker_line_out_of_range")
        if len(cited) > MAX_EVIDENCE_LINES:
            raise ModelOutputInvalidError("marker_too_many_lines")
        evidence = "\n".join(lines[n - 1].strip() for n in cited if lines[n - 1].strip())
        if point.awarded_marks > 0 and not evidence:
            raise ModelOutputInvalidError("marker_missing_evidence")
        proposals.append(
            PointProposal(
                point_id=point.point_id,
                awarded_marks=point.awarded_marks,
                evidence=evidence,
                confidence=point.confidence,
                error_category=point.error_category,
            )
        )
    order = {p.id: i for i, p in enumerate(question.points)}
    return tuple(sorted(proposals, key=lambda p: order[p.point_id]))
