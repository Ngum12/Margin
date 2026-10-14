import pytest

from app.services.page_counts import PageCountFlag, page_count_flag, typical_page_count


def test_typical_count_needs_three_scripts() -> None:
    assert typical_page_count([5, 5]) is None
    assert typical_page_count([5, 5, 9]) == 5
    assert typical_page_count([4, 5, 6, 7]) == 5  # lower median: a whole page count


@pytest.mark.parametrize(
    ("count", "typical", "flag"),
    [
        (5, 5, None),
        (6, 5, None),
        (4, 5, None),
        (7, 5, PageCountFlag.MORE_THAN_USUAL),  # tolerance max(2, round(2.5) = 2) = 2
        (3, 5, PageCountFlag.FEWER_THAN_USUAL),
        (12, 9, None),  # tolerance round(4.5) = 4 (round half to even)
        (13, 9, PageCountFlag.MORE_THAN_USUAL),
        (1, 5, PageCountFlag.NO_ANSWER_PAGES),
        (1, None, PageCountFlag.NO_ANSWER_PAGES),
        (9, None, None),  # too few scripts to judge
    ],
)
def test_flags(count: int, typical: int | None, flag: PageCountFlag | None) -> None:
    assert page_count_flag(count, typical) is flag
