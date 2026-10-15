"""The ``--orientation`` evaluation (Phase 4): judgements classed as fixed, left alone, wrong or
missed, with pages turned in memory only."""

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from app import cli
from app.ai.mock import MockReader
from app.ai.orientation_evaluation import (
    OrientationCase,
    OrientationPage,
    _appearance,
    evaluate_orientation,
)
from app.ai.types import ModelUnavailableError, PageImage, PageText
from app.ai.types import Transcription as AiTranscription
from app.config import get_settings
from app.subjects.registry import SubjectConfig, get_registry


def _case(expected: str, judged: str | None, confidence: float | None) -> OrientationCase:
    return OrientationCase("p.jpg", "chemistry", 0, expected, judged, confidence, 1.0, 0.8)


def test_each_judgement_is_classed_by_what_the_worker_would_do() -> None:
    assert _case("upside_down", "upside_down", 0.9).outcome == "fixed"
    assert _case("upright", "upright", 0.99).outcome == "left"
    assert _case("upright", "upside_down", 0.5).outcome == "left"  # too unsure to act
    assert _case("upright", "rotated_clockwise", 0.9).outcome == "wrong"
    assert _case("upside_down", "rotated_clockwise", 0.95).outcome == "wrong"
    assert _case("upside_down", "upright", 0.9).outcome == "missed"
    assert _case("upside_down", "upside_down", 0.7).outcome == "missed"
    assert _case("rotated_clockwise", None, None).outcome == "missed"


def test_turning_a_page_changes_how_it_looks() -> None:
    assert _appearance("upright", 90) == "rotated_clockwise"
    assert _appearance("upright", 180) == "upside_down"
    assert _appearance("upright", 270) == "rotated_counterclockwise"
    assert _appearance("upside_down", 0) == "upside_down"
    assert _appearance("rotated_clockwise", 270) == "upright"


class TurnSensingReader(MockReader):
    """Judges correctly from the turn it is given, except it misses quarter turns."""

    def __init__(self) -> None:
        super().__init__()
        self.turns: list[int] = []

    def transcribe(self, pages: list[PageImage], subject: SubjectConfig) -> AiTranscription:
        base = super().transcribe(pages, subject)
        turn = pages[0].rotation
        self.turns.append(turn)
        judged = {0: "upright", 180: "upside_down"}.get(turn, "upright")
        return AiTranscription(
            [PageText(pages[0].page_id, "x", judged, 0.9)],
            base.model,
            base.prompt_version,
            base.created_at,
        )


def test_pages_are_fed_turned_in_memory_and_counted(tmp_path: Path) -> None:
    path = tmp_path / "page.jpg"
    Image.new("RGB", (60, 80), "white").save(path, "JPEG")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = TurnSensingReader()
    chemistry = get_registry().get("cm_gce_ol", "chemistry")
    assert chemistry is not None

    summary = evaluate_orientation(
        reader,
        [OrientationPage(path, "chemistry"), OrientationPage(path, "chemistry", "upside_down")],
        lambda _code: chemistry,
        turns=(0, 90, 180, 270),
        threshold=0.8,
    )

    assert reader.turns == [0, 90, 180, 270, 0]  # the extra page is used as it is
    assert [c.outcome for c in summary.cases] == ["left", "missed", "fixed", "missed", "missed"]
    assert (summary.count("fixed"), summary.count("wrong"), summary.judged_right) == (1, 0, 2)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_cli_reports_the_orientation_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data" / "chemistry" / "student_1"
    data.mkdir(parents=True)
    Image.new("RGB", (60, 80), "white").save(data / "page1.jpg", "JPEG")
    (data / "truth.txt").write_text("1(a) text", encoding="utf-8")
    extra = tmp_path / "upside.jpg"
    Image.new("RGB", (60, 80), "white").save(extra, "JPEG")
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    report = tmp_path / "report.json"

    code = cli.main(
        [
            "evaluate",
            "--data",
            str(tmp_path / "data"),
            "--backend",
            "mock",
            "--orientation",
            "--orientation-extra",
            f"chemistry:upside_down:{extra}",
            "--report",
            str(report),
        ]
    )
    get_settings.cache_clear()

    assert code == 0
    assert "Orientation judgement" in capsys.readouterr().out
    orientation = json.loads(report.read_text(encoding="utf-8"))["models"][0]["orientation"]
    # The Mock reader always says "upright": the upright feed is left alone, the rest missed.
    assert (orientation["calls"], orientation["left"], orientation["missed"]) == (5, 1, 4)
    assert orientation["wrong"] == 0
    assert orientation["threshold"] == 0.8


def test_cli_rejects_a_malformed_extra_page(tmp_path: Path) -> None:
    data = tmp_path / "data" / "chemistry" / "student_1"
    data.mkdir(parents=True)
    Image.new("RGB", (60, 80), "white").save(data / "page1.jpg", "JPEG")
    (data / "truth.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(
            [
                "evaluate",
                "--data",
                str(tmp_path / "data"),
                "--backend",
                "mock",
                "--orientation",
                "--orientation-extra",
                "chemistry:sideways:missing.jpg",
            ]
        )


class FailingReader(MockReader):
    def __init__(self, error: str) -> None:
        super().__init__()
        self.error = error

    def transcribe(self, pages: list[PageImage], subject: SubjectConfig) -> AiTranscription:
        raise ModelUnavailableError(self.error)


@pytest.mark.parametrize(
    ("error", "recorded"), [("TimeoutError", "timeout"), ("http_500", "server_error")]
)
def test_a_reply_that_never_finishes_is_recorded_not_fatal(
    tmp_path: Path, error: str, recorded: str
) -> None:
    """Seen on upside-down pages (2026-10-15): the model rambles until the call times out."""
    path = tmp_path / "page.jpg"
    Image.new("RGB", (60, 80), "white").save(path, "JPEG")
    chemistry = get_registry().get("cm_gce_ol", "chemistry")
    assert chemistry is not None

    summary = evaluate_orientation(
        FailingReader(error),
        [OrientationPage(path, "chemistry")],
        lambda _code: chemistry,
        turns=(180,),
        threshold=0.8,
    )

    case = summary.cases[0]
    assert (case.judged, case.error, case.outcome) == (None, recorded, "missed")
    report = summary.as_json()
    assert report["no_valid_reply"] == 1


def test_a_server_that_is_down_still_stops_the_evaluation(tmp_path: Path) -> None:
    path = tmp_path / "page.jpg"
    Image.new("RGB", (60, 80), "white").save(path, "JPEG")
    chemistry = get_registry().get("cm_gce_ol", "chemistry")
    assert chemistry is not None
    with pytest.raises(ModelUnavailableError):
        evaluate_orientation(
            FailingReader("ConnectionRefusedError"),
            [OrientationPage(path, "chemistry")],
            lambda _code: chemistry,
            turns=(0,),
            threshold=0.8,
        )
