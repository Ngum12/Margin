"""Ollama Reader/Marker against a fake Ollama server: request shape, validation and retries."""

import base64
import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

from app.ai.ollama import OllamaMarker, OllamaReader, resolve_model
from app.ai.ollama_client import OllamaClient
from app.ai.types import (
    ExamSpec,
    ModelInfo,
    ModelOutputInvalidError,
    ModelUnavailableError,
    PageImage,
    PageText,
    PointSpec,
    QuestionSpec,
    Transcription,
)
from app.ai.validation import MARKER_SCHEMA, READER_SCHEMA
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
    model = resolve_model(client(fake), "qwen3-vl:8b-instruct")

    assert model == ModelInfo("qwen3-vl:8b-instruct", "sha256:ababa", "ollama")


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
        resolve_model(client(fake), "qwen3-vl:8b-instruct"),
        max_image_px=800,
        output_retries=0,
    )

    result = reader.transcribe([page], CHEMISTRY)

    assert result.pages[0].text == "H_2O is a compound"
    assert result.prompt_version.startswith("reader-v1#")
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
        ModelInfo("qwen3-vl:8b-instruct", "x", "ollama"),
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
        ModelInfo("qwen3-vl:8b-instruct", "x", "ollama"),
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
        client(fake), ModelInfo("qwen3-vl:8b-instruct", "x", "ollama"), output_retries=0
    )

    proposal = marker.mark(
        _answer("1(a) it conducts electricity\n1(b) hydrogen"), ExamSpec(CHEMISTRY, QUESTIONS)
    )

    assert [q.question_id for q in proposal.questions] == [1, 2]
    assert proposal.failed_question_ids == ()
    assert fake.requests[0]["format"] == MARKER_SCHEMA
    prompt = fake.requests[0]["messages"][0]["content"]
    assert "point_id 10" in prompt
    assert "Question 1(a)" in prompt
    assert "images" not in fake.requests[0]["messages"][0]


def test_marker_failure_on_one_question_is_reported_not_invented(fake: FakeOllama) -> None:
    invented = _points((10, 1, "metals are excellent conductors"), (11, 0, ""))
    fake.replies.extend([invented, invented, _points((20, 1, "hydrogen"))])
    marker = OllamaMarker(
        client(fake), ModelInfo("qwen3-vl:8b-instruct", "x", "ollama"), output_retries=1
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
    model = ModelInfo("qwen3-vl:8b-instruct", "x", "ollama")
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
