"""Ollama Reader/Marker against a fake Ollama server: request shape, validation and retries."""

import base64
import io
import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.ai.ollama import OllamaMarker, OllamaReader, resolve_model
from app.ai.ollama_client import OllamaClient
from app.ai.types import (
    ExamSpec,
    ModelCallTimeoutError,
    ModelInfo,
    ModelOutputInvalidError,
    ModelUnavailableError,
    PageImage,
    PageText,
    PointSpec,
    QuestionSpec,
    Transcription,
)
from app.ai.validation import READER_SCHEMA, marker_schema_for
from app.clock import utcnow
from app.subjects.registry import SubjectConfig, get_registry
from tests.fake_ollama import CUT_OFF, FakeOllama


def _chemistry() -> SubjectConfig:
    subject = get_registry().get("cm_gce_ol", "chemistry")
    if subject is None:  # pragma: no cover
        raise LookupError("chemistry config missing")
    return subject


CHEMISTRY = _chemistry()


@pytest.fixture
def fake() -> Iterator[FakeOllama]:
    with FakeOllama() as server:
        yield server


@pytest.fixture
def page(tmp_path: Path) -> PageImage:
    path = tmp_path / "page.jpg"
    Image.new("RGB", (1654, 2339), "white").save(path, "JPEG")
    return PageImage(1, path)


def client(fake: FakeOllama) -> OllamaClient:
    return OllamaClient(fake.url, timeout_seconds=5)


def test_resolve_model_uses_the_installed_digest(fake: FakeOllama) -> None:
    model = resolve_model(client(fake), "qwen3-vl:4b-instruct")

    assert model == ModelInfo("qwen3-vl:4b-instruct", "sha256:ababa", "ollama")


def test_missing_model_is_reported_as_unavailable(fake: FakeOllama) -> None:
    with pytest.raises(ModelUnavailableError, match="model_not_installed"):
        resolve_model(client(fake), "llama-nonexistent")


def test_unreachable_server_is_unavailable() -> None:
    dead = OllamaClient("http://127.0.0.1:9", timeout_seconds=1)  # discard port, nothing listens

    with pytest.raises(ModelUnavailableError):
        dead.list_models()


def test_reader_request_is_deterministic_schema_constrained_and_shrinks_images(
    fake: FakeOllama, page: PageImage
) -> None:
    fake.replies.append(json.dumps({"text": "H_2O is a compound"}))
    reader = OllamaReader(
        client(fake),
        resolve_model(client(fake), "qwen3-vl:4b-instruct"),
        max_image_px=800,
        output_retries=0,
    )

    result = reader.transcribe([page], CHEMISTRY)

    assert result.pages[0].text == "H_2O is a compound"
    assert result.prompt_version.startswith("reader-v2#")
    request = fake.requests[0]
    assert request["options"]["temperature"] == 0
    assert request["stream"] is False
    assert request["format"] == READER_SCHEMA
    message = request["messages"][0]
    assert "Never correct the student" in message["content"]
    assert "H_2O" in message["content"]  # subject notation hints included
    sent = Image.open(io.BytesIO(base64.b64decode(message["images"][0])))
    assert max(sent.size) == 800


def test_reader_retries_invalid_output_then_gives_up(fake: FakeOllama, page: PageImage) -> None:
    fake.replies.extend(["not json", '{"text": 3}', '{"wrong": "x"}'])
    reader = OllamaReader(
        client(fake),
        ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"),
        max_image_px=800,
        output_retries=2,
    )

    with pytest.raises(ModelOutputInvalidError):
        reader.transcribe([page], CHEMISTRY)
    assert len(fake.requests) == 3  # 1 try + 2 retries


def test_reader_recovers_when_a_retry_is_valid(fake: FakeOllama, page: PageImage) -> None:
    fake.replies.extend(["not json", '{"text": "ok"}'])
    reader = OllamaReader(
        client(fake),
        ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"),
        max_image_px=800,
        output_retries=2,
    )

    assert reader.transcribe([page], CHEMISTRY).pages[0].text == "ok"


QUESTIONS = (
    QuestionSpec(
        1,
        "1(a)",
        "Two properties of metals.",
        2,
        (PointSpec(10, "Conducts electricity", 1), PointSpec(11, "Malleable", 1)),
    ),
    QuestionSpec(2, "1(b)", "Gas with acid.", 1, (PointSpec(20, "Hydrogen", 1),)),
)


def _answer(text: str) -> Transcription:
    return Transcription([PageText(1, text)], ModelInfo("r", "1", "mock"), "reader", utcnow())


def _points(*items: tuple[int, int, str]) -> str:
    return json.dumps(
        {
            "points": [
                {
                    "point_id": p,
                    "awarded_marks": m,
                    "evidence": e,
                    "confidence": 0.7,
                    "error_category": "correct" if m else "omitted",
                }
                for p, m, e in items
            ]
        }
    )


def test_marker_marks_each_question_separately_with_schema(fake: FakeOllama) -> None:
    fake.replies.extend(
        [
            _points((10, 1, "conducts electricity"), (11, 0, "")),
            _points((20, 1, "hydrogen")),
        ]
    )
    marker = OllamaMarker(
        client(fake), ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"), output_retries=0
    )

    proposal = marker.mark(
        _answer("1(a) it conducts electricity\n1(b) hydrogen"), ExamSpec(CHEMISTRY, QUESTIONS)
    )

    assert [q.question_id for q in proposal.questions] == [1, 2]
    assert proposal.failed_question_ids == ()
    # A schema per question: exactly that question's points (owner, 2026-10-15).
    assert fake.requests[0]["format"] == marker_schema_for(QUESTIONS[0])
    assert fake.requests[1]["format"] == marker_schema_for(QUESTIONS[1])
    prompt = fake.requests[0]["messages"][0]["content"]
    assert "- p10 (1 mark): Conducts electricity" in prompt
    assert '"p10": {"awarded_marks": <0 to 1>' in prompt  # reply shape lists the keys
    assert "Question 1(a)" in prompt
    assert "images" not in fake.requests[0]["messages"][0]


def test_marker_failure_on_one_question_is_reported_not_invented(fake: FakeOllama) -> None:
    invented = _points((10, 1, "metals are excellent conductors"), (11, 0, ""))
    fake.replies.extend([invented, invented, _points((20, 1, "hydrogen"))])
    marker = OllamaMarker(
        client(fake), ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"), output_retries=1
    )

    proposal = marker.mark(
        _answer("1(a) it conducts\n1(b) hydrogen"), ExamSpec(CHEMISTRY, QUESTIONS)
    )

    assert proposal.failed_question_ids == (1,)
    assert [q.question_id for q in proposal.questions] == [2]


def test_prompts_never_contain_student_identity(fake: FakeOllama, page: PageImage) -> None:
    """The models see page images, notation hints, questions and the transcription only."""
    fake.replies.extend(
        [json.dumps({"text": "x"}), _points((10, 0, ""), (11, 0, "")), _points((20, 0, ""))]
    )
    model = ModelInfo("qwen3-vl:4b-instruct", "x", "ollama")
    OllamaReader(client(fake), model, max_image_px=800, output_retries=0).transcribe(
        [page], CHEMISTRY
    )
    OllamaMarker(client(fake), model, output_retries=0).mark(
        _answer("x"), ExamSpec(CHEMISTRY, QUESTIONS)
    )

    keys: set[str] = set()
    for request in fake.requests:
        keys |= set(request) | set(request["messages"][0])
    assert keys == {
        "model",
        "messages",
        "stream",
        "format",
        "options",
        "keep_alive",
        "role",
        "content",
        "images",
    }


def test_cut_off_reply_is_invalid_and_retried(fake: FakeOllama, page: PageImage) -> None:
    """A reply stopped by the output cap (e.g. a model that keeps "thinking") is never used."""
    fake.replies.extend([CUT_OFF + '{"text": "partial', '{"text": "complete"}'])
    reader = OllamaReader(
        client(fake), ModelInfo("qwen3-vl:4b", "x", "ollama"), max_image_px=800, output_retries=1
    )

    assert reader.transcribe([page], CHEMISTRY).pages[0].text == "complete"
    assert len(fake.requests) == 2


def test_cut_off_on_every_try_flags_invalid(fake: FakeOllama, page: PageImage) -> None:
    fake.replies.extend([CUT_OFF + "{", CUT_OFF + "{"])
    reader = OllamaReader(
        client(fake), ModelInfo("qwen3-vl:4b", "x", "ollama"), max_image_px=800, output_retries=1
    )

    with pytest.raises(ModelOutputInvalidError, match="output_cut_off"):
        reader.transcribe([page], CHEMISTRY)


def test_output_cap_context_and_think_are_sent(fake: FakeOllama, page: PageImage) -> None:
    capped = OllamaClient(fake.url, 5, think=False, max_output_tokens=512, context_tokens=8192)
    reader = OllamaReader(
        capped, ModelInfo("qwen3-vl:4b", "x", "ollama"), max_image_px=800, output_retries=0
    )

    reader.transcribe([page], CHEMISTRY)

    request = fake.requests[0]
    assert request["think"] is False
    assert request["options"] == {"temperature": 0, "num_predict": 512, "num_ctx": 8192}


def test_line_evidence_marker_numbers_the_answer_and_copies_lines(fake: FakeOllama) -> None:
    fake.replies.extend(
        [
            json.dumps(
                {
                    "points": [
                        {
                            "point_id": 10,
                            "awarded_marks": 1,
                            "evidence_lines": [1],
                            "confidence": 0.9,
                            "error_category": "correct",
                        },
                        {
                            "point_id": 11,
                            "awarded_marks": 0,
                            "evidence_lines": [],
                            "confidence": 0.6,
                            "error_category": "omitted",
                        },
                    ]
                }
            ),
            json.dumps(
                {
                    "points": [
                        {
                            "point_id": 20,
                            "awarded_marks": 1,
                            "evidence_lines": [2],
                            "confidence": 0.9,
                            "error_category": "correct",
                        },
                    ]
                }
            ),
        ]
    )
    marker = OllamaMarker(
        client(fake),
        ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"),
        output_retries=0,
        evidence="lines",
    )

    proposal = marker.mark(
        _answer("1(a) it conducts electricity\n1(b) hydrogen"), ExamSpec(CHEMISTRY, QUESTIONS)
    )

    prompt = fake.requests[0]["messages"][0]["content"]
    assert "L1: 1(a) it conducts electricity" in prompt
    assert fake.requests[0]["format"] == marker_schema_for(QUESTIONS[0], line_count=2)
    assert proposal.prompt_version.startswith("marker-lines-v2#")
    assert proposal.questions[0].points[0].evidence == "1(a) it conducts electricity"
    assert proposal.questions[1].points[0].evidence == "1(b) hydrogen"


# --- time-outs (owner, 2026-10-15) ------------------------------------------------------------


def _slow(seconds: float, reply: str) -> Callable[[dict[str, Any]], str]:
    def answer(_body: dict[str, Any]) -> str:
        time.sleep(seconds)
        return reply

    return answer


def test_a_slow_reply_is_invalid_output_not_an_unavailable_server(fake: FakeOllama) -> None:
    fake.replies.append(_slow(1.0, json.dumps({"text": "late"})))
    quick = OllamaClient(fake.url, timeout_seconds=0.3)
    with pytest.raises(ModelCallTimeoutError):
        quick.chat_json("qwen3-vl:4b-instruct", "p", READER_SCHEMA)


def test_a_server_that_cannot_be_reached_is_unavailable() -> None:
    # Nothing listens on port 9 (discard) on the test machine.
    with pytest.raises(ModelUnavailableError) as raised:
        OllamaClient("http://127.0.0.1:9", timeout_seconds=1).chat_json("m", "p", READER_SCHEMA)
    assert not isinstance(raised.value, ModelOutputInvalidError)


def test_reader_retries_a_time_out_once_only(fake: FakeOllama, page: PageImage) -> None:
    fake.replies.extend([_slow(1.0, "{}"), _slow(1.0, "{}"), json.dumps({"text": "never"})])
    reader = OllamaReader(
        OllamaClient(fake.url, timeout_seconds=0.3),
        ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"),
        max_image_px=800,
        output_retries=2,
    )
    with pytest.raises(ModelCallTimeoutError):
        reader.transcribe([page], CHEMISTRY)
    assert len(fake.requests) == 2  # 1 try + 1 retry, although 2 output retries are allowed


def test_reader_recovers_when_the_retry_after_a_time_out_is_valid(
    fake: FakeOllama, page: PageImage
) -> None:
    fake.replies.extend([_slow(1.0, "{}"), json.dumps({"text": "on time"})])
    reader = OllamaReader(
        OllamaClient(fake.url, timeout_seconds=0.3),
        ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"),
        max_image_px=800,
        output_retries=0,
    )
    assert reader.transcribe([page], CHEMISTRY).pages[0].text == "on time"


def test_marker_question_that_times_out_twice_is_reported_failed(fake: FakeOllama) -> None:
    fake.replies.extend([_slow(1.0, "{}"), _slow(1.0, "{}")])
    marker = OllamaMarker(
        OllamaClient(fake.url, timeout_seconds=0.3),
        ModelInfo("qwen3-vl:4b-instruct", "x", "ollama"),
        output_retries=2,
    )
    spec = ExamSpec(CHEMISTRY, (QuestionSpec(1, "1(a)", "q", 1, (PointSpec(10, "p", 1),)),))
    proposal = marker.mark(_answer("answer"), spec)
    assert proposal.failed_question_ids == (1,)
    assert len(fake.requests) == 2
