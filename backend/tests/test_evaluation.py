import json
from pathlib import Path

import pytest
from PIL import Image

from app import cli
from app.ai.evaluation import edit_distance, find_pages, key_tokens, normalise, score
from app.config import get_settings

MOCK_TEXT = (
    "1(a) Metals conduct electricity and they are malleable.\n1(b) Hydrogen gas H_2 is given off."
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

    assert (s.key_found, s.key_total) == (2, 4)  # one "=" and one "2" found of two each


def _dataset(root: Path, pages: dict[str, str]) -> None:
    for name, truth in pages.items():
        subject, stem = name.split("/")
        folder = root / subject
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 140), "white").save(folder / f"{stem}.jpg")
        (folder / f"{stem}.txt").write_text(truth, encoding="utf-8")


def test_find_pages_needs_ground_truth(tmp_path: Path) -> None:
    _dataset(tmp_path, {"chemistry/p1": "x"})
    Image.new("RGB", (10, 10)).save(tmp_path / "chemistry" / "no_truth.jpg")

    assert [img.name for img, _ in find_pages(tmp_path)["chemistry"]] == ["p1.jpg"]


def test_cli_evaluates_reader_per_subject_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _dataset(
        data,
        {
            "chemistry/p1": MOCK_TEXT,  # identical to what MockReader returns
            "chemistry/p2": MOCK_TEXT.replace("H_2", "H_3"),
            "mathematics/p1": "x^2 = 16",
        },
    )
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    report = tmp_path / "report.json"

    code = cli.main(["evaluate", "--data", str(data), "--backend", "mock", "--report", str(report)])
    get_settings.cache_clear()

    assert code == 0
    out = capsys.readouterr().out
    assert "chemistry" in out
    assert "mathematics" in out
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["reader"]["model"] == "mock-reader"
    assert result["reader"]["prompt_version"].startswith("reader-v1#")
    chemistry = next(s for s in result["subjects"] if s["subject"] == "chemistry")
    assert chemistry["pages"] == 2
    assert chemistry["page_results"][0]["cer"] == 0
    assert chemistry["page_results"][1]["cer"] == pytest.approx(1 / len(MOCK_TEXT))
    assert chemistry["page_results"][1]["key_token_recall"] < 1
    maths = next(s for s in result["subjects"] if s["subject"] == "mathematics")
    assert maths["key_token_recall"] == 0  # MockReader never writes x^2 = 16


def test_cli_rejects_unknown_subject_folder(tmp_path: Path) -> None:
    _dataset(tmp_path, {"astrology/p1": "x"})

    with pytest.raises(SystemExit, match="Unknown subject"):
        cli.main(["evaluate", "--data", str(tmp_path), "--backend", "mock"])
