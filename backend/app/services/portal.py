"""Released, confirmed work only. Student identifiers always come from the session."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db.models import (
    AnswerSheet,
    CoverSheet,
    ErrorCategory,
    Exam,
    ExamAbsence,
    Page,
    PageState,
    Question,
    Role,
    Script,
    ScriptStatus,
    Student,
    User,
)
from app.db.models.portal import RemarkRequest
from app.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.marks import from_half_marks
from app.schemas.portal import ReleaseIn, RemarkIn, RemarkReply
from app.services import audit, review
from app.services.access import get_visible_exam, get_visible_script, visible_exams
from app.services.results import script_results
from app.services.student_auth import policy


def own_script(db: Session, student: Student, script_id: int) -> tuple[Script, Exam]:
    script = db.get(Script, script_id)
    exam = db.get(Exam, script.exam_id) if script else None
    if (
        not script
        or script.student_id != student.id
        or script.status != ScriptStatus.CONFIRMED
        or not exam
        or exam.released_at is None
        or exam.school_class.school_id != student.school_id
    ):
        raise NotFoundError("Script")
    return script, exam


def release(db: Session, actor: User, exam_id: int, data: ReleaseIn) -> Exam:
    exam = get_visible_exam(db, actor, exam_id)
    if data.released:
        scripts = list(db.scalars(select(Script).where(Script.exam_id == exam.id)))
        expected = set(
            db.scalars(
                select(AnswerSheet.student_id).where(
                    AnswerSheet.exam_id == exam.id,
                    AnswerSheet.active.is_(True),
                    AnswerSheet.student_id.is_not(None),
                )
            )
        )
        expected.update(
            db.scalars(select(CoverSheet.student_id).where(CoverSheet.exam_id == exam.id))
        )
        expected.update(s.student_id for s in scripts)
        expected.update(db.scalars(select(Student.id).where(Student.class_id == exam.class_id)))
        absent = set(
            db.scalars(select(ExamAbsence.student_id).where(ExamAbsence.exam_id == exam.id))
        )
        confirmed = {s.student_id for s in scripts if s.status == ScriptStatus.CONFIRMED}
        if (
            not scripts
            or expected - absent - confirmed
            or any(
                s.status != ScriptStatus.CONFIRMED and s.student_id not in absent for s in scripts
            )
        ):
            raise ConflictError(
                "Confirm every script or record the student's absence", code="portal.not_ready"
            )
    before = {
        "released_at": exam.released_at.isoformat() if exam.released_at else None,
        "visibility": exam.student_visibility,
    }
    # Changing visibility cannot extend the remark window. Unrelease/release is audited.
    exam.released_at = (exam.released_at or utcnow()) if data.released else None
    exam.released_by_id = actor.id if data.released else None
    exam.student_visibility = data.visibility
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="release" if data.released else "unrelease",
        old_value=before,
        new_value={
            "released_at": exam.released_at.isoformat() if exam.released_at else None,
            "visibility": data.visibility,
        },
    )
    return exam


def detail(db: Session, student: Student, script_id: int) -> dict[str, Any]:
    script, exam = own_script(db, student, script_id)
    result = script_results(db, exam, [script], with_pages=True)[0]
    notes = exam.student_visibility != "marks"
    scheme = exam.student_visibility == "scheme"
    rules = policy(db, student.school_id)
    average = None
    if rules.class_average:
        peers = list(
            db.scalars(
                select(Script).where(
                    Script.exam_id == exam.id, Script.status == ScriptStatus.CONFIRMED
                )
            )
        )
        totals = [r.total_half for r in script_results(db, exam, peers) if r.total_half is not None]
        average = sum(totals) / len(totals) / 2 if totals else None
    return {
        "class_average": average,
        "id": script.id,
        "exam_id": exam.id,
        "title": exam.title,
        "subject": exam.subject_code,
        "date": str(exam.exam_date) if exam.exam_date else str(exam.created_at.date()),
        "total": from_half_marks(result.total_half or 0),
        "maximum": from_half_marks(result.max_half),
        "visibility": exam.student_visibility,
        "released_at": exam.released_at,
        "remark_days": rules.remark_days,
        "remark_max": rules.remark_max,
        "escalation": rules.escalation,
        "questions": [
            {
                "id": q.question.id,
                "label": q.question.label,
                "prompt": q.question.prompt_text,
                "marks": from_half_marks(q.final_half or 0),
                "maximum": from_half_marks(q.question.max_half_marks),
                "comment": q.comment if notes else "",
                "feedback": [
                    {
                        "category": p.final_category,
                        "evidence": p.evidence,
                        "pages": result.pages_for_question(q.question.id),
                    }
                    for p in q.points
                    if p.final_half != p.max_half
                ]
                if notes
                else [],
                "scheme": [
                    {
                        "description": p.description,
                        "marks": from_half_marks(p.half_marks),
                        "alternatives": p.alternatives,
                        "rules": p.rules,
                    }
                    for p in q.question.points
                ]
                if scheme
                else [],
            }
            for q in result.questions
        ],
        "pages": [
            {"id": p.page.id, "position": p.page.position, "rotation": p.page.effective_rotation}
            for p in result.pages
            if not p.page.is_cover
        ],
        "remarks": [
            remark_out(r)
            for r in db.scalars(select(RemarkRequest).where(RemarkRequest.script_id == script.id))
        ],
    }


def my_exams(db: Session, student: Student) -> list[dict[str, Any]]:
    ids = db.scalars(
        select(Script.id)
        .join(Exam)
        .where(
            Script.student_id == student.id,
            Script.status == ScriptStatus.CONFIRMED,
            Exam.released_at.is_not(None),
        )
        .order_by(Exam.exam_date.desc(), Exam.id.desc())
    )
    return [detail(db, student, script_id) for script_id in ids]


def remark_out(r: RemarkRequest) -> dict[str, Any]:
    return {
        "id": r.id,
        "script_id": r.script_id,
        "question_id": r.question_id,
        "reason": r.reason,
        "message": r.message,
        "page_id": r.page_id,
        "location": r.location,
        "status": r.status,
        "escalated_once": r.escalated_once,
        "awaiting_hod": r.awaiting_hod,
        "responses": r.responses,
        "unread": bool(
            r.responses and (r.student_seen_at is None or r.student_seen_at < r.updated_at)
        ),
    }


def request_remark(db: Session, student: Student, script_id: int, data: RemarkIn) -> RemarkRequest:
    script, exam = own_script(db, student, script_id)
    rules = policy(db, student.school_id)
    if exam.released_at is None or utcnow() > exam.released_at + timedelta(days=rules.remark_days):
        raise ConflictError("Remark window has closed", code="portal.remark_closed")
    existing = list(db.scalars(select(RemarkRequest).where(RemarkRequest.script_id == script.id)))
    if len(existing) >= rules.remark_max or any(
        r.question_id == data.question_id for r in existing
    ):
        raise ConflictError("Remark request limit reached", code="portal.remark_limit")
    question = db.get(Question, data.question_id)
    if not question or question.exam_id != exam.id:
        raise NotFoundError("Question")
    if data.page_id is not None:
        page = db.get(Page, data.page_id)
        if not page or page.script_id != script.id or page.state != PageState.ASSIGNED:
            raise NotFoundError("Page")
    r = RemarkRequest(
        script_id=script.id,
        question_id=question.id,
        student_id=student.id,
        reason=data.reason,
        message=data.message.strip(),
        page_id=data.page_id,
        location={"x": data.x, "y": data.y} if data.x is not None and data.y is not None else None,
    )
    db.add(r)
    db.flush()
    if data.reason == "total_error":
        result = script_results(db, exam, [script])[0]
        # Totals are computed from the current confirmed point decisions, never cached.
        r.status = "answered"
        r.responses = [
            {
                "automatic": True,
                "code": "total_correct",
                "total": from_half_marks(result.total_half or 0),
                "at": utcnow().isoformat(),
            }
        ]
    audit.record(
        db,
        actor=None,
        entity_type="remark_request",
        entity_id=r.id,
        action="request_remark",
        new_value={"student_id": student.id, "question_id": question.id, "reason": data.reason},
    )
    return r


def student_remark(db: Session, student: Student, remark_id: int) -> RemarkRequest:
    r = db.get(RemarkRequest, remark_id)
    if not r or r.student_id != student.id:
        raise NotFoundError("Remark")
    own_script(db, student, r.script_id)
    return r


def escalate(db: Session, student: Student, remark_id: int) -> RemarkRequest:
    r = student_remark(db, student, remark_id)
    if not policy(db, student.school_id).escalation or r.status != "answered" or r.escalated_once:
        raise ConflictError("Escalation unavailable")
    r.escalated_once = True
    r.awaiting_hod = True
    r.status = "sent"
    audit.record(
        db,
        actor=None,
        entity_type="remark_request",
        entity_id=r.id,
        action="escalate",
        new_value={"student_id": student.id},
    )
    return r


def staff_requests(db: Session, actor: User) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(RemarkRequest)
        .join(Script)
        .where(Script.exam_id.in_(visible_exams(actor).with_only_columns(Exam.id)))
        .order_by(RemarkRequest.created_at)
    )
    return [{**remark_out(r), "exam_id": db.get(Script, r.script_id).exam_id} for r in rows]  # type: ignore[union-attr]


def staff_remark(db: Session, actor: User, remark_id: int) -> RemarkRequest:
    r = db.get(RemarkRequest, remark_id)
    if not r:
        raise NotFoundError("Remark")
    get_visible_script(db, actor, r.script_id)
    if r.awaiting_hod and actor.role not in (Role.ADMIN, Role.HEAD_OF_DEPARTMENT):
        raise PermissionDeniedError("Head of department reply required")
    return r


def reply(db: Session, actor: User, remark_id: int, data: RemarkReply) -> RemarkRequest:
    r = staff_remark(db, actor, remark_id)
    if r.status == "answered":
        raise ConflictError("Already answered")
    script = get_visible_script(db, actor, r.script_id)
    exam = get_visible_exam(db, actor, script.exam_id)
    if script.status != ScriptStatus.CONFIRMED:
        raise ConflictError("Confirm the script before replying")
    before = script_results(db, exam, [script])[0]
    old = before.total_half
    old_points = {p.point_id: p.final_half for q in before.questions for p in q.points}
    if data.marks:
        review.reopen(db, actor, script.id, reason=data.message)
        question = db.get(Question, r.question_id)
        allowed = {p.id for p in question.points} if question else set()
        for point_id, marks in data.marks.items():
            if point_id not in allowed:
                raise NotFoundError("Point")
            review.set_decision(
                db, actor, script.id, point_id, marks, ErrorCategory.CONCEPTUAL_ERROR
            )
        review.confirm(db, actor, script.id)
    after = script_results(db, exam, [script])[0]
    new = after.total_half
    new_points = {p.point_id: p.final_half for q in after.questions for p in q.points}
    r.responses = [
        *r.responses,
        {
            "automatic": False,
            "message": data.message,
            "actor_id": actor.id,
            "role": actor.role.value,
            "at": utcnow().isoformat(),
            "old_marks": from_half_marks(old or 0),
            "new_marks": from_half_marks(new or 0),
            "changed": old_points != new_points,
        },
    ]
    r.status = "answered"
    r.awaiting_hod = False
    audit.record(
        db,
        actor=actor,
        entity_type="remark_request",
        entity_id=r.id,
        action="reply",
        old_value={"total_half": old},
        new_value={"total_half": new, "point_marks": data.marks},
        reason=data.message,
    )
    return r
