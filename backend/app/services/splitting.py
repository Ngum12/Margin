"""Decide where each scanned page goes. Pure logic, no database or files.

Rules (D-029): a page is assigned to a student only when it is that student's cover sheet for
this exam, read from a valid QR code, or an answer page that follows such a cover in scan order.
Everything else goes to the unassigned tray with a reason. Nothing is ever assigned by guess.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from app.db.models import UnassignedReason
from app.pdf.runner import RenderedPage
from app.sheets.tokens import PayloadProblem, parse_payload


@dataclass(frozen=True)
class SheetOwner:
    exam_id: int
    student_id: int | None
    page_number: int | None = None
    sheet_id: int | None = None


@dataclass(frozen=True)
class Placement:
    index: int
    is_cover: bool
    student_id: int | None  # set when the page is assigned
    reason: UnassignedReason | None  # set when the page goes to the tray
    related_index: int | None = None  # the problem cover that this page follows
    detected_exam_id: int | None = None
    # Clockwise degrees from the most recent cover's QR orientation (orientation layer b).
    rotation_stack: int = 0
    page_number: int | None = None
    sheet_id: int | None = None


class _Kind(Enum):
    ANSWER_SHEET = "answer_sheet"
    ANSWER = "answer"
    GOOD_COVER = "good_cover"
    PROBLEM_COVER = "problem_cover"


@dataclass(frozen=True)
class _Classified:
    kind: _Kind
    page_number: int | None = None
    sheet_id: int | None = None
    student_id: int | None = None
    reason: UnassignedReason | None = None
    detected_exam_id: int | None = None


def _classify(
    page: RenderedPage,
    exam_id: int,
    lookup: Callable[[str], SheetOwner | None],
) -> _Classified:
    texts = page.qr_texts
    if len(texts) > 1:
        return _Classified(_Kind.PROBLEM_COVER, reason=UnassignedReason.QR_CONFLICT)
    if len(texts) == 1:
        parsed = parse_payload(texts[0])
        if parsed.problem is PayloadProblem.NOT_OURS:
            # Some other QR code (e.g. printed on a question paper). Only a framed page is a cover.
            if page.cover_frame:
                return _Classified(_Kind.PROBLEM_COVER, reason=UnassignedReason.QR_NOT_OURS)
            return _Classified(_Kind.ANSWER)
        if parsed.problem is PayloadProblem.BAD_CHECKSUM or parsed.token is None:
            return _Classified(_Kind.PROBLEM_COVER, reason=UnassignedReason.QR_BAD_CHECKSUM)
        owner = lookup(parsed.token)
        if owner is None:
            return _Classified(_Kind.PROBLEM_COVER, reason=UnassignedReason.UNKNOWN_SHEET)
        if owner.exam_id != exam_id:
            return _Classified(
                _Kind.PROBLEM_COVER,
                reason=UnassignedReason.OTHER_EXAM,
                detected_exam_id=owner.exam_id,
            )
        if owner.sheet_id is not None:
            return _Classified(
                _Kind.ANSWER_SHEET,
                student_id=owner.student_id,
                page_number=owner.page_number,
                sheet_id=owner.sheet_id,
            )
        return _Classified(_Kind.GOOD_COVER, student_id=owner.student_id)
    if page.qr_damaged:
        return _Classified(_Kind.PROBLEM_COVER, reason=UnassignedReason.QR_DAMAGED)
    if page.cover_frame:
        return _Classified(_Kind.PROBLEM_COVER, reason=UnassignedReason.QR_UNREADABLE)
    return _Classified(_Kind.ANSWER)


def place_pages(
    pages: list[RenderedPage],
    *,
    exam_id: int,
    lookup: Callable[[str], SheetOwner | None],
    students_with_pages: set[int],
    received_pages: set[tuple[int, int]] | None = None,
) -> list[Placement]:
    """Place pages in scan order.

    ``lookup`` maps a token to its sheet owner. ``students_with_pages`` holds students who already
    have pages from earlier uploads of this exam; their sheets are not merged automatically.
    """
    received_pages = received_pages or set()
    seen_sheet_pages: set[tuple[int, int]] = set()
    placements: list[Placement] = []
    seen_in_upload: set[int] = set()
    current_student: int | None = None
    problem_cover: int | None = None  # index of the problem cover the current run follows
    # A stack is usually fed the same way up, so a cover's orientation applies to the answer
    # pages after it until the next cover. A cover without a readable code resets it to 0.
    stack_rotation = 0

    for page in sorted(pages, key=lambda p: p.index):
        info = _classify(page, exam_id, lookup)
        if info.kind is not _Kind.ANSWER:
            stack_rotation = page.qr_rotation
        rotation = stack_rotation

        if info.kind is _Kind.ANSWER_SHEET:
            current_student, problem_cover = None, page.index
            key = (info.student_id or 0, info.page_number or 0)
            issue = None
            if info.student_id is None:
                issue = UnassignedReason.SPARE_SHEET
            elif key in received_pages:
                issue = UnassignedReason.ALREADY_UPLOADED
            elif key in seen_sheet_pages:
                issue = UnassignedReason.DUPLICATE_IN_UPLOAD
            seen_sheet_pages.add(key)
            placements.append(
                Placement(
                    page.index,
                    False,
                    info.student_id if issue is None else None,
                    issue,
                    rotation_stack=page.qr_rotation,
                    page_number=info.page_number,
                    sheet_id=info.sheet_id,
                )
            )
            continue

        if info.kind is _Kind.GOOD_COVER and info.student_id is not None:
            reason: UnassignedReason | None = None
            if info.student_id in seen_in_upload:
                reason = UnassignedReason.DUPLICATE_IN_UPLOAD
            elif info.student_id in students_with_pages:
                reason = UnassignedReason.ALREADY_UPLOADED
            if reason is None:
                seen_in_upload.add(info.student_id)
                current_student, problem_cover = info.student_id, None
                placements.append(
                    Placement(page.index, True, info.student_id, None, rotation_stack=rotation)
                )
            else:
                current_student, problem_cover = None, page.index
                placements.append(
                    Placement(page.index, True, None, reason, rotation_stack=rotation)
                )
            continue

        if info.kind is _Kind.PROBLEM_COVER:
            current_student, problem_cover = None, page.index
            placements.append(
                Placement(
                    page.index,
                    True,
                    None,
                    info.reason,
                    detected_exam_id=info.detected_exam_id,
                    rotation_stack=rotation,
                )
            )
            continue

        # Answer page.
        if current_student is not None:
            placements.append(
                Placement(page.index, False, current_student, None, rotation_stack=rotation)
            )
        elif problem_cover is not None:
            placements.append(
                Placement(
                    page.index,
                    False,
                    None,
                    UnassignedReason.FOLLOWS_UNASSIGNED_COVER,
                    related_index=problem_cover,
                    rotation_stack=rotation,
                )
            )
        else:
            placements.append(
                Placement(page.index, False, None, UnassignedReason.BEFORE_FIRST_COVER)
            )
    return placements
