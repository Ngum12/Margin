"""Mark units. All marks are stored as integer half marks (D-018).

The API and UI accept whole marks only for now. Allowing half marks later means changing
``HALF_MARKS_ALLOWED`` and the UI inputs; stored data does not change.
"""

HALF_MARKS_PER_MARK = 2
HALF_MARKS_ALLOWED = False


def to_half_marks(marks: int) -> int:
    return marks * HALF_MARKS_PER_MARK


def from_half_marks(half_marks: int) -> int | float:
    """Whole numbers come back as ``int`` so the API shows ``3``, not ``3.0``."""
    if half_marks % HALF_MARKS_PER_MARK == 0:
        return half_marks // HALF_MARKS_PER_MARK
    return half_marks / HALF_MARKS_PER_MARK
