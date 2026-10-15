"""Teacher review (Phase 4): marking queue, script review, edits, confirm and reopen.

Every edit returns the whole updated review, so the screen always shows what is stored."""

from fastapi import APIRouter

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.schemas.common import ApiModel
from app.schemas.review import (
    AcceptAllOut,
    CommentIn,
    DecisionIn,
    HeartbeatOut,
    QueueOut,
    RerunOut,
    RotationIn,
    ScriptReviewOut,
    TranscriptionIn,
)
from app.services import ai_marking, review
from app.services.access import get_visible_script
from app.services.red_pen import script_red_pen
from app.services.uploads import get_visible_page

router = APIRouter(tags=["review"])


def _review_of_page(db: DbSession, user: CurrentUser, page_id: int) -> ScriptReviewOut | None:
    page = get_visible_page(db, user, page_id)
    return review.script_review(db, user, page.script_id) if page.script_id else None


@router.get("/exams/{exam_id}/queue")
def queue(exam_id: int, db: DbSession, user: CurrentUser) -> QueueOut:
    return review.queue(db, user, exam_id)


@router.get("/scripts/{script_id}/review")
def script_review(script_id: int, db: DbSession, user: CurrentUser) -> ScriptReviewOut:
    return review.script_review(db, user, script_id)


@router.post("/scripts/{script_id}/review-heartbeat")
def heartbeat(script_id: int, db: DbSession, user: CurrentUser) -> HeartbeatOut:
    session = review.heartbeat(db, user, script_id)
    return HeartbeatOut(
        session_open=session is not None,
        active_seconds=session.active_seconds if session else 0.0,
    )


@router.put("/scripts/{script_id}/decisions/{point_id}")
def set_decision(
    script_id: int, point_id: int, body: DecisionIn, db: DbSession, user: CurrentUser
) -> ScriptReviewOut:
    review.set_decision(db, user, script_id, point_id, body.marks, body.category)
    return review.script_review(db, user, script_id)


@router.post("/scripts/{script_id}/decisions/{point_id}/accept")
def accept_point(
    script_id: int, point_id: int, db: DbSession, user: CurrentUser
) -> ScriptReviewOut:
    review.accept_point(db, user, script_id, point_id)
    return review.script_review(db, user, script_id)


@router.post("/scripts/{script_id}/accept-all")
def accept_all(script_id: int, db: DbSession, user: CurrentUser) -> AcceptAllOut:
    accepted = review.accept_all(db, user, script_id)
    return AcceptAllOut(accepted=accepted, review=review.script_review(db, user, script_id))


@router.put("/scripts/{script_id}/questions/{question_id}/comment")
def set_comment(
    script_id: int, question_id: int, body: CommentIn, db: DbSession, user: CurrentUser
) -> ScriptReviewOut:
    review.set_comment(db, user, script_id, question_id, body.text)
    return review.script_review(db, user, script_id)


@router.post("/scripts/{script_id}/rerun-ai", status_code=202)
def rerun_script(
    script_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> ScriptReviewOut:
    """Start a new AI run for one unconfirmed script; earlier results stay as history."""
    ai_marking.rerun_visible_script(db, user, script_id, settings)
    return review.script_review(db, user, script_id)


@router.post("/exams/{exam_id}/rerun-ai", status_code=202)
def rerun_exam(exam_id: int, db: DbSession, user: CurrentUser, settings: AppSettings) -> RerunOut:
    """Re-run AI marking for every unconfirmed script of the exam."""
    return RerunOut(scripts_queued=ai_marking.rerun_visible_exam(db, user, exam_id, settings))


@router.post("/scripts/{script_id}/confirm")
def confirm(script_id: int, db: DbSession, user: CurrentUser) -> ScriptReviewOut:
    review.confirm(db, user, script_id)
    return review.script_review(db, user, script_id)


@router.post("/scripts/{script_id}/reopen")
def reopen(script_id: int, db: DbSession, user: CurrentUser) -> ScriptReviewOut:
    review.reopen(db, user, script_id)
    return review.script_review(db, user, script_id)


@router.post("/pages/{page_id}/transcription")
def edit_transcription(
    page_id: int, body: TranscriptionIn, db: DbSession, user: CurrentUser
) -> ScriptReviewOut | None:
    review.edit_transcription(db, user, page_id, body.text)
    return _review_of_page(db, user, page_id)


@router.post("/pages/{page_id}/rotation")
def set_rotation(
    page_id: int, body: RotationIn, db: DbSession, user: CurrentUser
) -> ScriptReviewOut | None:
    review.set_rotation(db, user, page_id, body.rotation)
    return _review_of_page(db, user, page_id)


@router.post("/pages/{page_id}/undo-auto-rotation")
def undo_auto_rotation(page_id: int, db: DbSession, user: CurrentUser) -> ScriptReviewOut | None:
    review.undo_auto_rotation(db, user, page_id)
    return _review_of_page(db, user, page_id)


@router.post("/pages/{page_id}/retranscribe", status_code=202)
def retranscribe(
    page_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> ScriptReviewOut | None:
    review.request_retranscription(db, user, page_id, settings)
    return _review_of_page(db, user, page_id)


# --- red pen (owner, 2026-10-15) ----------------------------------------------------------------


class RedPenMarkOut(ApiModel):
    kind: str
    x: float
    y: float
    size: float
    text: str
    width: float
    question_id: int | None
    point_id: int | None
    pending: bool


class RedPenCommentOut(ApiModel):
    question_id: int
    label: str
    comment: str


class RedPenPageOut(ApiModel):
    page_id: int
    placed: bool
    marks: list[RedPenMarkOut]
    unplaced_comments: list[RedPenCommentOut]


class RedPenOut(ApiModel):
    total: str
    pages: list[RedPenPageOut]


@router.get("/scripts/{script_id}/red-pen")
def red_pen(script_id: int, db: DbSession, user: CurrentUser, settings: AppSettings) -> RedPenOut:
    """Where the red pen marks go on each answer page (fractions of the upright page)."""
    script = get_visible_script(db, user, script_id)
    layout = script_red_pen(db, script, settings.data_dir, language=user.preferred_language.value)
    return RedPenOut(
        total=layout.total,
        pages=[
            RedPenPageOut(
                page_id=page_id,
                placed=page.placed,
                marks=[RedPenMarkOut(**mark.__dict__) for mark in page.marks],
                unplaced_comments=[
                    RedPenCommentOut(question_id=q.question_id, label=q.label, comment=q.comment)
                    for q in page.unplaced_comments
                ],
            )
            for page_id, page in layout.pages.items()
        ],
    )
