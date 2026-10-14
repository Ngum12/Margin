"""Unit tests for page placement: every rule, without images or a database."""

from app.db.models import UnassignedReason as R
from app.pdf.runner import RenderedPage
from app.services.splitting import Placement, SheetOwner, place_pages
from app.sheets.tokens import payload_for

EXAM = 1
OTHER_EXAM = 2
TOKENS = {
    "AAAAAAAAAAAAAAAA": SheetOwner(EXAM, 10),
    "BBBBBBBBBBBBBBBB": SheetOwner(EXAM, 11),
    "CCCCCCCCCCCCCCCC": SheetOwner(OTHER_EXAM, 12),
}


def cover(index: int, token: str, *, frame: bool = True) -> RenderedPage:
    return RenderedPage(
        index, f"{index}.jpg", f"t{index}.jpg", 10, 10, 0, [payload_for(token)], 0, frame
    )


def answer(index: int) -> RenderedPage:
    return RenderedPage(index, f"{index}.jpg", f"t{index}.jpg", 10, 10, 0, [], 0, False)


def page(
    index: int, *, texts: list[str] | None = None, damaged: int = 0, frame: bool = False
) -> RenderedPage:
    return RenderedPage(
        index, f"{index}.jpg", f"t{index}.jpg", 10, 10, 0, texts or [], damaged, frame
    )


def place(pages: list[RenderedPage], already: set[int] | None = None) -> list[Placement]:
    return place_pages(pages, exam_id=EXAM, lookup=TOKENS.get, students_with_pages=already or set())


def summary(placements: list[Placement]) -> list[tuple[int, object]]:
    return [(p.index, p.student_id if p.student_id is not None else p.reason) for p in placements]


def test_covers_start_scripts_and_answers_follow() -> None:
    result = place([cover(0, "A" * 16), answer(1), answer(2), cover(3, "B" * 16), answer(4)])

    assert summary(result) == [(0, 10), (1, 10), (2, 10), (3, 11), (4, 11)]
    assert [p.is_cover for p in result] == [True, False, False, True, False]


def test_pages_before_first_cover_go_to_tray() -> None:
    assert summary(place([answer(0), cover(1, "A" * 16)])) == [(0, R.BEFORE_FIRST_COVER), (1, 10)]


def test_other_exam_sheet_and_its_pages_go_to_tray() -> None:
    result = place([cover(0, "A" * 16), answer(1), cover(2, "C" * 16), answer(3), answer(4)])

    assert summary(result) == [
        (0, 10),
        (1, 10),
        (2, R.OTHER_EXAM),
        (3, R.FOLLOWS_UNASSIGNED_COVER),
        (4, R.FOLLOWS_UNASSIGNED_COVER),
    ]
    assert result[2].detected_exam_id == OTHER_EXAM
    assert result[3].related_index == 2


def test_duplicate_sheet_in_one_upload_is_not_merged() -> None:
    result = place([cover(0, "A" * 16), answer(1), cover(2, "A" * 16), answer(3)])

    assert summary(result) == [
        (0, 10),
        (1, 10),
        (2, R.DUPLICATE_IN_UPLOAD),
        (3, R.FOLLOWS_UNASSIGNED_COVER),
    ]


def test_student_with_pages_from_earlier_upload_is_not_merged() -> None:
    result = place([cover(0, "A" * 16), answer(1)], already={10})

    assert summary(result) == [(0, R.ALREADY_UPLOADED), (1, R.FOLLOWS_UNASSIGNED_COVER)]


def test_unknown_token_goes_to_tray() -> None:
    assert summary(place([cover(0, "D" * 16), answer(1)])) == [
        (0, R.UNKNOWN_SHEET),
        (1, R.FOLLOWS_UNASSIGNED_COVER),
    ]


def test_bad_checksum_goes_to_tray() -> None:
    bad = payload_for("A" * 16)[:-4] + "ZZZZ"
    assert summary(place([page(0, texts=[bad])])) == [(0, R.QR_BAD_CHECKSUM)]


def test_damaged_qr_goes_to_tray_even_without_frame() -> None:
    assert summary(place([cover(0, "A" * 16), page(1, damaged=2), answer(2)])) == [
        (0, 10),
        (1, R.QR_DAMAGED),
        (2, R.FOLLOWS_UNASSIGNED_COVER),
    ]


def test_framed_page_without_qr_is_an_unreadable_cover() -> None:
    assert summary(place([cover(0, "A" * 16), page(1, frame=True), answer(2)])) == [
        (0, 10),
        (1, R.QR_UNREADABLE),
        (2, R.FOLLOWS_UNASSIGNED_COVER),
    ]


def test_two_different_valid_codes_on_one_page_conflict() -> None:
    texts = sorted([payload_for("A" * 16), payload_for("B" * 16)])
    assert summary(place([page(0, texts=texts, frame=True)])) == [(0, R.QR_CONFLICT)]


def test_foreign_qr_on_an_unframed_page_is_an_answer_page() -> None:
    result = place([cover(0, "A" * 16), page(1, texts=["https://example.org"])])

    assert summary(result) == [(0, 10), (1, 10)]


def test_foreign_qr_on_a_framed_page_is_a_problem_cover() -> None:
    assert summary(place([page(0, texts=["https://example.org"], frame=True)])) == [
        (0, R.QR_NOT_OURS)
    ]


def test_good_cover_after_a_problem_resumes_assignment() -> None:
    result = place([page(0, frame=True), answer(1), cover(2, "B" * 16), answer(3)])

    assert summary(result) == [
        (0, R.QR_UNREADABLE),
        (1, R.FOLLOWS_UNASSIGNED_COVER),
        (2, 11),
        (3, 11),
    ]


def test_pages_are_placed_in_scan_order_whatever_the_input_order() -> None:
    result = place([answer(1), cover(0, "A" * 16)])

    assert summary(result) == [(0, 10), (1, 10)]
