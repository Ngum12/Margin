"""Deterministic stand-ins for the models: tests, development and demos without a GPU.

They follow exactly the same contract as the real models, including validation of their own
output, so the whole pipeline is exercised.
"""

import json
import re
import time

from app.ai.prompts import load_prompt
from app.ai.types import (
    ExamSpec,
    MarkingProposal,
    ModelInfo,
    PageImage,
    PageText,
    QuestionProposal,
    Transcription,
)
from app.ai.validation import parse_marker_output, parse_reader_output
from app.clock import utcnow
from app.db.models import ErrorCategory
from app.subjects.registry import SubjectConfig

MOCK_VERSION = "mock-1"
_WORD = re.compile(r"[A-Za-z0-9_^+\-]{4,}")


class MockReader:
    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay = delay_seconds
        self.model = ModelInfo("mock-reader", MOCK_VERSION, "mock")
        self.prompt_version = load_prompt("reader").version

    def transcribe(self, pages: list[PageImage], subject: SubjectConfig) -> Transcription:
        texts = []
        for page in pages:
            if self._delay:
                time.sleep(self._delay)
            if page.sidecar_text is not None and page.sidecar_text.is_file():
                text = page.sidecar_text.read_text(encoding="utf-8")
            else:
                text = (
                    "1(a) Metals conduct electricity and they are malleable.\n"
                    "1(b) Hydrogen gas H_2 is given off."
                )
            raw = json.dumps({"text": text})  # same path as a real model reply
            texts.append(PageText(page.page_id, parse_reader_output(raw)))
        return Transcription(texts, self.model, self.prompt_version, utcnow())


class MockMarker:
    """Awards a point when one of its key words appears in the answer and quotes that word."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay = delay_seconds
        self.model = ModelInfo("mock-marker", MOCK_VERSION, "mock")
        self.prompt_version = load_prompt("marker").version

    def mark(self, transcription: Transcription, exam: ExamSpec) -> MarkingProposal:
        answer = transcription.full_text
        lowered = answer.casefold()
        questions = []
        for question in exam.questions:
            if self._delay:
                time.sleep(self._delay)
            points = []
            for point in question.points:
                keywords = [
                    w
                    for text in (point.description, *point.alternatives)
                    for w in _WORD.findall(text)
                ]
                hit = next((w for w in keywords if w.casefold() in lowered), None)
                if hit is not None:
                    start = lowered.index(hit.casefold())
                    evidence = answer[start : start + len(hit)]
                    points.append(
                        {
                            "point_id": point.id,
                            "awarded_marks": point.marks,
                            "evidence": evidence,
                            "confidence": 0.9,
                            "error_category": ErrorCategory.CORRECT.value,
                        }
                    )
                else:
                    points.append(
                        {
                            "point_id": point.id,
                            "awarded_marks": 0,
                            "evidence": "",
                            "confidence": 0.6,
                            "error_category": ErrorCategory.OMITTED.value,
                        }
                    )
            raw = json.dumps({"points": points})
            questions.append(
                QuestionProposal(question.id, parse_marker_output(raw, question, answer))
            )
        return MarkingProposal(tuple(questions), self.model, self.prompt_version, utcnow())
