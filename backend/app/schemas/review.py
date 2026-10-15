"""Teacher review (Phase 4): marking queue and script review. Marks are whole marks (D-018)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.db.models import ErrorCategory, ExamStatus, ScriptStatus, TranscriptionSource
from app.schemas.common import ApiModel
from app.services.page_counts import PageCountFlag

Marks = int | float

COMMENT_MAX_LENGTH = 300
TRANSCRIPTION_MAX_LENGTH = 20_000


# --- input ----------------------------------------------------------------------------------


class DecisionIn(ApiModel):
    """Either field may be left out to keep its current value; at least one must be given."""

    marks: Marks | None = None
    category: ErrorCategory | None = None


class CommentIn(ApiModel):
    # Length is checked in the service so the error has a translated code.
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class TranscriptionIn(ApiModel):
    text: Annotated[str, StringConstraints(max_length=TRANSCRIPTION_MAX_LENGTH)]


class RotationIn(ApiModel):
    # Clockwise degrees; null resets to the automatic orientation.
    rotation: Literal[0, 90, 180, 270] | None


# --- marking queue (screen 6) ----------------------------------------------------------------


class QueueItemOut(ApiModel):
    script_id: int
    student_code: str
    student_name: str | None
    status: ScriptStatus
    manual_reason: str | None
    # The teacher can open it: AI finished (or flagged for manual marking), or confirmed.
    reviewable: bool
    page_count: int
    page_count_flag: PageCountFlag | None
    auto_rotated_pages: int
    min_confidence: float | None
    uncertain_points: int
    # Points where the AI proposed fewer marks than the point's maximum, and the marks deducted.
    deductions: int
    marks_deducted: Marks
    decided_points: int
    total_points: int
    proposed_total: Marks | None
    final_total: Marks | None
    max_total: Marks
    # Review time over finished (confirmed) sessions. Local data only, never sent anywhere.
    review_seconds: float | None
    active_seconds: float | None


class QueueOut(ApiModel):
    exam_id: int
    exam_title: str
    exam_status: ExamStatus
    items: list[QueueItemOut]
    typical_page_count: int | None
    confirmed_count: int
    # Class averages over confirmed scripts with recorded review time (owner change 2).
    timed_count: int
    average_review_seconds: float | None
    average_active_seconds: float | None


# --- script review (screen 7) ----------------------------------------------------------------


class TranscriptionVersionOut(ApiModel):
    id: int
    text: str
    source: TranscriptionSource
    model_name: str | None
    prompt_version: str | None
    rotation: int
    created_at: datetime


class ReviewPageOut(ApiModel):
    id: int
    position: int | None
    is_cover: bool
    width: int
    height: int
    # Clockwise degrees to turn the stored image for display (see Page.effective_rotation).
    rotation: int
    rotation_teacher: int | None
    rotation_auto: int
    auto_rotated: bool
    auto_rotation_confidence: float | None
    rotated_after_transcription: bool
    retranscribe_pending: bool
    transcription: TranscriptionVersionOut | None
    # Every version, oldest first.
    versions: list[TranscriptionVersionOut]
    # A teacher changed the text after the AI marked the script.
    edited_after_marking: bool


class ReviewPointOut(ApiModel):
    id: int
    position: int
    description: str
    alternatives: list[str]
    max_marks: Marks
    decision_id: int | None
    proposed_marks: Marks | None
    evidence: str
    confidence: float | None
    error_category: ErrorCategory | None
    # Marks below the point's maximum in the AI's proposal (0 when none; owner, 2026-10-15).
    deducted: Marks
    final_marks: Marks | None
    final_category: ErrorCategory | None
    decided_at: datetime | None


class ReviewQuestionOut(ApiModel):
    id: int
    label: str
    prompt_text: str
    max_marks: Marks
    points: list[ReviewPointOut]
    comment: str
    proposed_total: Marks | None
    # Sum of final marks, capped at the question's maximum; None until a point is decided.
    final_total: Marks | None
    deductions: int
    marks_deducted: Marks


class ReviewScriptOut(ApiModel):
    id: int
    status: ScriptStatus
    manual_reason: str | None
    student_code: str
    student_name: str | None
    reviewed_at: datetime | None
    confirmed_at: datetime | None


class ReviewExamOut(ApiModel):
    id: int
    title: str
    subject_code: str


class ReviewNavigationOut(ApiModel):
    previous_id: int | None
    next_id: int | None
    position: int
    count: int


class ReviewTotalsOut(ApiModel):
    max_total: Marks
    proposed_total: Marks | None
    final_total: Marks | None
    decided_points: int
    total_points: int
    deductions: int
    marks_deducted: Marks


class ScriptReviewOut(ApiModel):
    script: ReviewScriptOut
    exam: ReviewExamOut
    ready: bool
    locked: bool
    can_confirm: bool
    pages: list[ReviewPageOut]
    questions: list[ReviewQuestionOut]
    totals: ReviewTotalsOut
    navigation: ReviewNavigationOut
    marked_on_earlier_text: bool


class HeartbeatOut(ApiModel):
    session_open: bool
    active_seconds: float = Field(ge=0)


class AcceptAllOut(ApiModel):
    accepted: int
    review: ScriptReviewOut
