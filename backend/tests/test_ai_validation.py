import json
from typing import Any

import pytest

from app.ai.prompts import load_prompt
from app.ai.types import ModelOutputInvalidError, PointSpec, QuestionSpec
from app.ai.validation import (
    answer_lines,
    evidence_is_quoted,
    numbered_answer,
    parse_marker_lines_output,
    parse_marker_output,
    parse_reader_output,
)
from app.db.models import ErrorCategory

QUESTION = QuestionSpec(
    id=1,
    label="1(a)",
    prompt_text="State two properties of metals.",
    max_marks=2,
    points=(PointSpec(10, "Conducts electricity", 1), PointSpec(11, "Malleable", 1)),
)
ANSWER = "1(a) metals conduct electrisity and they are maleable"


def point(
    point_id: int, marks: int = 1, evidence: str = "conduct electrisity", **extra: Any
) -> dict[str, Any]:
    return {
        "point_id": point_id,
        "awarded_marks": marks,
        "evidence": evidence,
        "confidence": 0.8,
        "error_category": "language_expression",
        **extra,
    }


def marker(*points: dict[str, Any]) -> str:
    return json.dumps({"points": list(points)})


def test_reader_output_accepts_text_and_keeps_errors() -> None:
    assert parse_reader_output('{"text": "H_2O is a elemnt"}').text == "H_2O is a elemnt"


@pytest.mark.parametrize(
    "raw", ["not json", "{}", '{"text": 5}', '{"text": "a", "extra": 1}', '["text"]']
)
def test_reader_output_rejects_anything_else(raw: str) -> None:
    with pytest.raises(ModelOutputInvalidError):
        parse_reader_output(raw)


def test_valid_marker_output() -> None:
    result = parse_marker_output(
        marker(point(11, evidence="maleable"), point(10)), QUESTION, ANSWER
    )

    assert [p.point_id for p in result] == [10, 11]  # mark scheme order
    assert result[0].error_category is ErrorCategory.LANGUAGE_EXPRESSION


def test_evidence_matches_ignoring_case_and_spacing() -> None:
    assert evidence_is_quoted("Conduct   ELECTRISITY", ANSWER)
    assert not evidence_is_quoted("conduct electricity", ANSWER)  # corrected spelling: not a quote


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (marker(point(10)), "marker_points_mismatch"),  # a point missing
        (marker(point(10), point(11, evidence="maleable"), point(12)), "marker_points_mismatch"),
        (marker(point(10), point(10)), "marker_points_mismatch"),  # duplicated
        (marker(point(10, marks=2), point(11, evidence="maleable")), "marker_marks_out_of_range"),
        (marker(point(10, evidence=""), point(11, evidence="maleable")), "marker_missing_evidence"),
        (
            marker(
                point(10, evidence="metals are good conductors"), point(11, evidence="maleable")
            ),
            "marker_invented_evidence",
        ),
        (marker(point(10, marks="1"), point(11, evidence="maleable")), "marker_schema"),  # type: ignore[arg-type]
        (marker(point(10, marks=1.0), point(11, evidence="maleable")), "marker_schema"),  # type: ignore[arg-type]
        (marker(point(10, confidence=1.5), point(11, evidence="maleable")), "marker_schema"),
        (
            marker(point(10, error_category="wrong"), point(11, evidence="maleable")),
            "marker_schema",
        ),
        (marker(point(10, note="x"), point(11, evidence="maleable")), "marker_schema"),
        ("{not json", "not_json"),
    ],
)
def test_invalid_marker_output_is_rejected(raw: str, reason: str) -> None:
    with pytest.raises(ModelOutputInvalidError, match=reason):
        parse_marker_output(raw, QUESTION, ANSWER)


def test_zero_marks_may_have_no_evidence() -> None:
    result = parse_marker_output(
        marker(
            point(10, marks=0, evidence="", error_category="omitted"),
            point(11, evidence="maleable"),
        ),
        QUESTION,
        ANSWER,
    )
    assert result[0].awarded_marks == 0


def test_prompt_version_changes_with_content() -> None:
    reader = load_prompt("reader")
    marker_prompt = load_prompt("marker")

    assert reader.version.startswith("reader-v2#")
    assert marker_prompt.version.startswith("marker-v1#")
    assert len(reader.version.split("#")[1]) == 8
    assert "{subject_hints}" not in reader.render(subject_hints="")
    assert '{"text"' in reader.render(subject_hints="")  # JSON example braces kept


# --- line-number evidence (D-047) ---------------------------------------------------------------

LINES = ["1(a) metals conduct electrisity", "and they are maleable", "1(b) hydrogen"]


def lines_marker(*points: dict[str, Any]) -> str:
    return json.dumps({"points": list(points)})


def lpoint(
    point_id: int, marks: int = 1, lines: list[int] | None = None, **extra: Any
) -> dict[str, Any]:
    return {
        "point_id": point_id,
        "awarded_marks": marks,
        "evidence_lines": [1] if lines is None else lines,
        "confidence": 0.8,
        "error_category": "language_expression",
        **extra,
    }


def test_line_evidence_is_copied_verbatim_by_margin() -> None:
    result = parse_marker_lines_output(
        lines_marker(lpoint(10, lines=[1]), lpoint(11, lines=[2, 2])), QUESTION, LINES
    )

    assert result[0].evidence == "1(a) metals conduct electrisity"  # student's spelling kept
    assert result[1].evidence == "and they are maleable"  # duplicates collapsed


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (lines_marker(lpoint(10, lines=[0]), lpoint(11)), "marker_line_out_of_range"),
        (lines_marker(lpoint(10, lines=[4]), lpoint(11)), "marker_line_out_of_range"),
        (lines_marker(lpoint(10, lines=[]), lpoint(11)), "marker_missing_evidence"),
        (
            lines_marker(lpoint(10, lines=[1, 2, 3, 1, 2, 3, 4]), lpoint(11)),
            "marker_line_out_of_range",
        ),
        (lines_marker(lpoint(10)), "marker_points_mismatch"),
        (lines_marker(lpoint(10, marks=2), lpoint(11)), "marker_marks_out_of_range"),
        (lines_marker(lpoint(10, evidence="quoted"), lpoint(11)), "marker_schema"),
    ],
)
def test_invalid_line_evidence_is_rejected(raw: str, reason: str) -> None:
    with pytest.raises(ModelOutputInvalidError, match=reason):
        parse_marker_lines_output(raw, QUESTION, LINES)


def test_too_many_cited_lines_is_rejected() -> None:
    many = [f"line {i}" for i in range(1, 10)]
    with pytest.raises(ModelOutputInvalidError, match="marker_too_many_lines"):
        parse_marker_lines_output(
            lines_marker(lpoint(10, lines=list(range(1, 8))), lpoint(11)), QUESTION, many
        )


def test_zero_marks_need_no_lines() -> None:
    result = parse_marker_lines_output(
        lines_marker(
            lpoint(10, marks=0, lines=[], error_category="omitted"), lpoint(11, lines=[2])
        ),
        QUESTION,
        LINES,
    )
    assert result[0].evidence == ""


def test_numbered_answer() -> None:
    assert numbered_answer(answer_lines("a\r\nb")) == "L1: a\nL2: b"


def test_reader_output_carries_a_valid_orientation_judgement() -> None:
    out = parse_reader_output(
        '{"text": "x", "orientation": "upside_down", "orientation_confidence": 0.93}'
    )
    assert (out.text, out.orientation, out.orientation_confidence) == ("x", "upside_down", 0.93)


@pytest.mark.parametrize(
    "judgement",
    [
        '"orientation": "sideways", "orientation_confidence": 0.9',
        '"orientation": "upside_down", "orientation_confidence": 1.5',
        '"orientation": "upside_down", "orientation_confidence": true',
        '"orientation": "upside_down"',
    ],
)
def test_invalid_orientation_judgement_keeps_the_text_and_rotates_nothing(judgement: str) -> None:
    out = parse_reader_output('{"text": "kept", ' + judgement + "}")
    assert (out.text, out.orientation, out.orientation_confidence) == ("kept", None, None)
