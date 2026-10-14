from typing import Any

import pytest

from app.marks import HALF_MARKS_ALLOWED, from_half_marks, to_half_marks
from app.schemas.mark_scheme import MarkSchemeIn
from app.services.mark_scheme import total_marks, validate_mark_scheme
from tests.factories import complete_scheme


def _scheme(**question_overrides: Any) -> MarkSchemeIn:
    data = complete_scheme()
    data["questions"][0].update(question_overrides)
    return MarkSchemeIn.model_validate(data)


def _codes(issues: list[Any]) -> list[str]:
    return [i.code for i in issues]


def test_complete_scheme_is_ready() -> None:
    report = validate_mark_scheme(MarkSchemeIn.model_validate(complete_scheme()))

    assert report.is_ready
    assert report.can_save
    assert report.notices == []


def test_total_marks_is_sum_of_question_maximums() -> None:
    assert total_marks(MarkSchemeIn.model_validate(complete_scheme())) == 3


def test_empty_scheme_can_be_saved_but_is_not_ready() -> None:
    report = validate_mark_scheme(MarkSchemeIn(questions=[]))

    assert report.can_save
    assert _codes(report.readiness) == ["exam.no_questions"]


@pytest.mark.parametrize("label", ["", "   "])
def test_label_is_required(label: str) -> None:
    report = validate_mark_scheme(_scheme(label=label))

    assert _codes(report.blocking) == ["question.label_required"]
    assert report.blocking[0].path == ["questions", 0, "label"]


def test_label_length_is_limited() -> None:
    assert _codes(validate_mark_scheme(_scheme(label="x" * 21)).blocking) == [
        "question.label_too_long"
    ]


def test_labels_are_unique_ignoring_case() -> None:
    report = validate_mark_scheme(_scheme(label="1(B)"))

    assert _codes(report.blocking) == ["question.label_duplicate"]
    assert report.blocking[0].path == ["questions", 1, "label"]
    assert report.blocking[0].params == {"label": "1(b)", "first": 1}


@pytest.mark.parametrize("max_marks", [0, -1, 101])
def test_question_maximum_must_be_between_1_and_100(max_marks: int) -> None:
    assert "question.max_marks_invalid" in _codes(
        validate_mark_scheme(_scheme(max_marks=max_marks)).blocking
    )


@pytest.mark.parametrize("marks", [0, -2, 101])
def test_point_marks_must_be_between_1_and_100(marks: int) -> None:
    data = complete_scheme()
    data["questions"][0]["points"][0]["marks"] = marks

    report = validate_mark_scheme(MarkSchemeIn.model_validate(data))

    assert _codes(report.blocking) == ["point.marks_invalid"]
    assert report.blocking[0].path == ["questions", 0, "points", 0, "marks"]


def test_question_without_points_is_not_ready() -> None:
    report = validate_mark_scheme(_scheme(points=[]))

    assert report.can_save
    assert _codes(report.readiness) == ["question.no_points"]


def test_points_below_maximum_make_full_marks_unreachable() -> None:
    report = validate_mark_scheme(_scheme(max_marks=5))

    assert report.can_save
    assert not report.is_ready
    assert _codes(report.readiness) == ["question.points_below_max"]
    assert report.readiness[0].params == {"label": "1(a)", "points_total": 2, "max_marks": 5}


def test_points_above_maximum_are_allowed_with_a_notice() -> None:
    """'Any 1 of 2 points' style questions: points total 2, maximum 1."""
    report = validate_mark_scheme(_scheme(max_marks=1))

    assert report.is_ready
    assert _codes(report.notices) == ["question.points_exceed_max"]


def test_point_description_is_needed_to_be_ready() -> None:
    data = complete_scheme()
    data["questions"][0]["points"][1]["description"] = "  "

    report = validate_mark_scheme(MarkSchemeIn.model_validate(data))

    assert report.can_save
    assert _codes(report.readiness) == ["point.description_required"]


def test_too_many_questions_blocks_saving() -> None:
    question = complete_scheme()["questions"][1]
    data = {"questions": [{**question, "label": str(i)} for i in range(101)]}

    assert "exam.too_many_questions" in _codes(
        validate_mark_scheme(MarkSchemeIn.model_validate(data)).blocking
    )


def test_marks_use_half_mark_units() -> None:
    assert not HALF_MARKS_ALLOWED  # whole marks only in v1 (D-018)
    assert to_half_marks(3) == 6
    assert from_half_marks(6) == 3
    assert isinstance(from_half_marks(6), int)
    assert from_half_marks(5) == 2.5
