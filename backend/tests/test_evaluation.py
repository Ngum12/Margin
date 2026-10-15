import json
from pathlib import Path

import pytest
from PIL import Image

from app import cli
from app.ai.evaluation import edit_distance, find_scripts, key_tokens, normalise, score
from app.ai.marking_evaluation import (
    Expected,
    MarkingSummary,
    QuestionComparison,
    compare_script,
    exam_spec_from_csv,
    load_expected,
)
from app.ai.mock import MockMarker
from app.ai.types import ExamSpec
from app.config import get_settings
from app.subjects.registry import get_registry

MOCK_TEXT = (
    "1(a) Metals conduct electricity and they are malleable.\n1(b) Hydrogen gas H_2 is given off."
)
SCHEME = (
    "question_label,question_prompt,question_max_marks,point_description,point_marks,point_alternatives\n"
    "1a,Properties of metals,2,Conducts electricity,1,\n"
    "1a,Properties of metals,2,Malleable,1,\n"
    "1b,Gas given off,1,Hydrogen,1,\n"
)


def test_edit_distance() -> None:
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == 3
    assert edit_distance(["a", "b"], ["a", "b"]) == 0


def test_cer_and_wer_keep_case_and_spelling() -> None:
    s = score("the cat sat", "the Cat sat")

    assert s.char_edits == 1
    assert s.cer == pytest.approx(1 / 11)
    assert s.wer == pytest.approx(1 / 3)


def test_line_endings_and_trailing_spaces_do_not_count() -> None:
    assert score("a b\nc", "a b  \r\nc\n").char_edits == 0
    assert normalise(" x \r\n y ") == "x\n y"


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("H_2O and CO_2", ["H_2O", "CO_2"]),
        ("2H_2 + O_2 -> 2H_2O", ["2", "H_2", "+", "O_2", "->", "2", "H_2O"]),
        ("x^2 = 16, so x = 4", ["x^2", "=", "16", "=", "4"]),
        ("Na^+ and SO_4^2-", ["Na^+", "SO_4^2-"]),
        ("a well-known 3.5 % rise of 1/2", ["3.5", "1/2"]),
        ("N_2 + 3H_2 <=> 2NH_3", ["N_2", "+", "3", "H_2", "<=>", "2", "NH_3"]),
    ],
)
def test_key_tokens(text: str, tokens: list[str]) -> None:
    assert key_tokens(text) == tokens


def test_key_token_recall_counts_multisets() -> None:
    s = score("x = 2 and y = 2", "x = 2 and y 3")

    assert (s.key_found, s.key_total) == (2, 4)


def _image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "white").save(path)


def test_find_scripts_reads_student_folders_and_page_pairs(tmp_path: Path) -> None:
    _image(tmp_path / "chemistry" / "student_2" / "page10.jpg")
    _image(tmp_path / "chemistry" / "student_2" / "page2.jpg")
    (tmp_path / "chemistry" / "student_2" / "truth.txt").write_text("x", encoding="utf-8")
    _image(tmp_path / "chemistry" / "student_9" / "page1.jpg")  # no truth: skipped
    _image(tmp_path / "chemistry" / "loose.jpg")
    (tmp_path / "chemistry" / "loose.txt").write_text("y", encoding="utf-8")

    scripts = find_scripts(tmp_path)["chemistry"]

    assert [s.name for s in scripts] == ["student_2", "loose"]
    assert [p.name for p in scripts[0].images] == ["page2.jpg", "page10.jpg"]  # natural order


def _spec(tmp_path: Path) -> ExamSpec:
    path = tmp_path / "margin_chemistry_term1.csv"
    path.write_text(SCHEME, encoding="utf-8")
    chemistry = get_registry().get("cm_gce_ol", "chemistry")
    assert chemistry is not None
    return exam_spec_from_csv(path, chemistry)


def test_compare_script_caps_and_matches_questions(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    expected = {
        ("chemistry", "s1", "1a"): Expected(2, "language_expression"),
        ("chemistry", "s1", "1b"): Expected(1, "correct"),
    }

    comparisons, _ = compare_script(
        MockMarker(), spec, "chemistry", "s1", "it conducts electricity, it is malleable", expected
    )

    assert [(c.question, c.expected, c.proposed) for c in comparisons] == [
        ("1a", 2, 2),
        ("1b", 1, 0),
    ]


def test_summary_metrics_separate_language_cases() -> None:
    summary = MarkingSummary(
        [
            QuestionComparison("c", "s1", "1", 2, "language_expression", 1, ("conceptual_error",)),
            QuestionComparison("c", "s1", "2", 3, "language_expression", 3),
            QuestionComparison("c", "s1", "3", 1, "correct", 1),
            QuestionComparison("c", "s1", "4", 2, "correct", None),  # marker failed
        ],
        [1.0, 3.0],
    )

    assert summary.questions() == 4
    assert summary.failed() == 1
    assert summary.exact_agreement() == pytest.approx(2 / 4)
    assert summary.mean_absolute_difference() == pytest.approx(1 / 3)
    assert summary.exact_agreement(language_only=True) == pytest.approx(1 / 2)
    assert summary.marks_lost(language_only=True) == 1
    assert summary.language_called_conceptual() == 1
    assert summary.seconds_per_script == 2.0


def test_load_expected(tmp_path: Path) -> None:
    path = tmp_path / "expected.csv"
    path.write_text(
        "subject,student,profile,question,expected_marks,category,note\n"
        'chemistry,student_2,"weak English, correct ideas",1A,2,language_expression,"x, y"\n',
        encoding="utf-8",
    )

    assert load_expected(path) == {
        ("chemistry", "student_2", "1a"): Expected(2, "language_expression")
    }


def test_cli_evaluates_reading_and_marking_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    for student, truth in {
        "student_1": MOCK_TEXT,
        "student_2": MOCK_TEXT.replace("H_2", "H_3"),
    }.items():
        _image(data / "chemistry" / student / "page1.jpg")
        (data / "chemistry" / student / "truth.txt").write_text(truth, encoding="utf-8")
    schemes = tmp_path / "schemes"
    schemes.mkdir()
    (schemes / "margin_chemistry_term1.csv").write_text(SCHEME, encoding="utf-8")
    expected = tmp_path / "expected.csv"
    expected.write_text(
        "subject,student,question,expected_marks,category\n"
        "chemistry,student_1,1a,2,correct\nchemistry,student_1,1b,1,correct\n"
        "chemistry,student_2,1a,2,language_expression\nchemistry,student_2,1b,1,correct\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    report = tmp_path / "report.json"

    code = cli.main(
        [
            "evaluate",
            "--data",
            str(data),
            "--backend",
            "mock",
            "--mark-schemes",
            str(schemes),
            "--expected-marks",
            str(expected),
            "--report",
            str(report),
        ]
    )
    get_settings.cache_clear()

    assert code == 0
    out = capsys.readouterr().out
    assert "Marking vs expected marks" in out
    result = json.loads(report.read_text(encoding="utf-8"))
    model = result["models"][0]
    assert model["model"] == "mock"
    assert model["prompt_version"].startswith("reader-v1#")
    scripts = model["reading"][0]["scripts"]
    assert scripts[0]["cer"] == 0  # identical to what MockReader returns
    assert scripts[1]["cer"] == pytest.approx(1 / len(MOCK_TEXT))
    marking = model["marking"]
    assert set(marking) == {"reader", "truth"}
    assert marking["truth"]["questions"] == 4
    assert marking["truth"]["language_expression"]["questions"] == 1


def test_cli_rejects_unknown_subject_folder(tmp_path: Path) -> None:
    _image(tmp_path / "astrology" / "s1" / "page1.jpg")
    (tmp_path / "astrology" / "s1" / "truth.txt").write_text("x", encoding="utf-8")

    with pytest.raises(SystemExit, match="Unknown subject"):
        cli.main(["evaluate", "--data", str(tmp_path), "--backend", "mock"])


def test_evaluation_resumes_from_its_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rerun must reuse finished calls (the overnight run is resumable) instead of calling
    the model again. Regression: an empty cache counted as false and nothing was saved."""
    data = tmp_path / "data"
    _image(data / "chemistry" / "student_1" / "page1.jpg")
    (data / "chemistry" / "student_1" / "truth.txt").write_text(MOCK_TEXT, encoding="utf-8")
    schemes = tmp_path / "schemes"
    schemes.mkdir()
    (schemes / "margin_chemistry_term1.csv").write_text(SCHEME, encoding="utf-8")
    expected = tmp_path / "expected.csv"
    expected.write_text(
        "subject,student,question,expected_marks,category\nchemistry,student_1,1a,2,correct\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    args = [
        "evaluate",
        "--data",
        str(data),
        "--backend",
        "mock",
        "--mark-schemes",
        str(schemes),
        "--expected-marks",
        str(expected),
        "--report",
        str(tmp_path / "report.json"),
    ]

    assert cli.main(args) == 0
    cache = tmp_path / "report.cache.jsonl"
    assert len(cache.read_text(encoding="utf-8").splitlines()) == 3  # 1 read + 2 marking passes

    def must_not_be_called(*_args: object) -> object:
        raise AssertionError("model called although the result was cached")

    monkeypatch.setattr("app.ai.mock.MockReader.transcribe", must_not_be_called)
    monkeypatch.setattr("app.ai.mock.MockMarker.mark", must_not_be_called)
    capsys.readouterr()
    assert cli.main(args) == 0
    get_settings.cache_clear()
    out = capsys.readouterr().out
    assert "(3 finished calls)" in out
    assert out.count("(cached)") == 3


def test_both_evidence_designs_share_one_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _image(data / "chemistry" / "student_1" / "page1.jpg")
    (data / "chemistry" / "student_1" / "truth.txt").write_text(MOCK_TEXT, encoding="utf-8")
    schemes = tmp_path / "schemes"
    schemes.mkdir()
    (schemes / "margin_chemistry_term1.csv").write_text(SCHEME, encoding="utf-8")
    expected = tmp_path / "expected.csv"
    expected.write_text(
        "subject,student,question,expected_marks,category\nchemistry,student_1,1a,2,correct\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    report = tmp_path / "report.json"

    code = cli.main(
        [
            "evaluate",
            "--data",
            str(data),
            "--backend",
            "mock",
            "--mark-schemes",
            str(schemes),
            "--expected-marks",
            str(expected),
            "--evidence",
            "quote,lines",
            "--report",
            str(report),
        ]
    )
    get_settings.cache_clear()

    assert code == 0
    out = capsys.readouterr().out
    assert out.count("  read chemistry/student_1/page1.jpg") == 1  # read once, marked twice
    assert "mock [quote]" in out
    assert "mock [lines]" in out
    models = json.loads(report.read_text(encoding="utf-8"))["models"]
    assert [m["evidence"] for m in models] == ["quote", "lines"]
    assert models[1]["marker_prompt_version"].startswith("marker-lines-v1#")
    lines_marking = models[1]["marking"]["truth"]
    assert lines_marking["questions"] == 1
    assert lines_marking["failed"] == 0
