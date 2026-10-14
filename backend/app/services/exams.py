"""Exams and their mark schemes. Marks cross this boundary as whole marks and are stored as
half-mark units (D-018)."""

from datetime import date

from sqlalchemy.orm import Session, selectinload

from app.db.models import Exam, ExamStatus, MarkSchemePoint, Question, SchoolClass, User
from app.errors import ConflictError, Issue, ValidationFailedError
from app.marks import from_half_marks, to_half_marks
from app.schemas.mark_scheme import MarkSchemeIn, PointIn, QuestionIn
from app.services import audit
from app.services.access import get_visible_class, get_visible_exam, visible_exams
from app.services.mark_scheme import MarkSchemeReport, validate_mark_scheme
from app.services.uploads import has_uploads
from app.subjects.registry import get_registry

# Status changes allowed in Phase 1. Later phases add marking/reviewing/completed transitions.
_ALLOWED_TRANSITIONS = {
    (ExamStatus.DRAFT, ExamStatus.READY),
    (ExamStatus.READY, ExamStatus.DRAFT),
}
_DETAILS_EDITABLE = {ExamStatus.DRAFT, ExamStatus.READY}


def _check_subject(actor: User, subject_code: str) -> None:
    if get_registry().get(actor.school.curriculum, subject_code) is None:
        raise ValidationFailedError(
            "Unknown subject for this school's curriculum",
            code="exam.subject_unknown",
            issues=[Issue("exam.subject_unknown", ["subject_code"])],
        )


def scheme_of(exam: Exam) -> MarkSchemeIn:
    """The stored mark scheme in whole-mark API form."""
    return MarkSchemeIn(
        questions=[
            QuestionIn(
                label=q.label,
                prompt_text=q.prompt_text,
                max_marks=int(from_half_marks(q.max_half_marks)),
                points=[
                    PointIn(
                        description=p.description,
                        marks=int(from_half_marks(p.half_marks)),
                        alternatives=list(p.alternatives),
                    )
                    for p in q.points
                ],
            )
            for q in exam.questions
        ]
    )


def validation_of(exam: Exam) -> MarkSchemeReport:
    return validate_mark_scheme(scheme_of(exam))


def total_half_marks(exam: Exam) -> int:
    return sum(q.max_half_marks for q in exam.questions)


def _details(exam: Exam) -> dict[str, object]:
    return {
        "title": exam.title,
        "subject_code": exam.subject_code,
        "exam_date": exam.exam_date.isoformat() if exam.exam_date else None,
        "class_id": exam.class_id,
    }


def list_exams(db: Session, actor: User) -> list[Exam]:
    return list(
        db.scalars(
            visible_exams(actor)
            .options(selectinload(Exam.questions), selectinload(Exam.school_class))
            .order_by(Exam.updated_at.desc())
        )
    )


def get_exam(db: Session, actor: User, exam_id: int) -> Exam:
    return get_visible_exam(db, actor, exam_id)


def create_exam(
    db: Session,
    actor: User,
    *,
    class_id: int,
    subject_code: str,
    title: str,
    exam_date: date | None,
) -> Exam:
    school_class: SchoolClass = get_visible_class(db, actor, class_id)
    _check_subject(actor, subject_code)
    exam = Exam(
        class_id=school_class.id,
        subject_code=subject_code,
        title=title,
        exam_date=exam_date,
        status=ExamStatus.DRAFT,
        created_by_id=actor.id,
    )
    db.add(exam)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="create",
        new_value=_details(exam),
    )
    return exam


def update_exam_details(db: Session, actor: User, exam_id: int, changes: dict[str, object]) -> Exam:
    exam = get_visible_exam(db, actor, exam_id)
    if exam.status not in _DETAILS_EDITABLE:
        raise ConflictError("Exam details can no longer be changed", code="exam.locked")
    if "subject_code" in changes:
        if exam.status != ExamStatus.DRAFT and changes["subject_code"] != exam.subject_code:
            raise ConflictError(
                "The subject can only change while the exam is a draft", code="exam.locked"
            )
        _check_subject(actor, str(changes["subject_code"]))
    before = _details(exam)
    for field in ("title", "subject_code"):
        if changes.get(field) is not None:
            setattr(exam, field, changes[field])
    if "exam_date" in changes:
        value = changes["exam_date"]
        exam.exam_date = value if isinstance(value, date) else None
    after = _details(exam)
    if after != before:
        audit.record(
            db,
            actor=actor,
            entity_type="exam",
            entity_id=exam.id,
            action="update_details",
            old_value=before,
            new_value=after,
        )
    return exam


def replace_mark_scheme(
    db: Session, actor: User, exam_id: int, scheme: MarkSchemeIn
) -> tuple[Exam, MarkSchemeReport]:
    exam = get_visible_exam(db, actor, exam_id)
    if exam.status != ExamStatus.DRAFT:
        raise ConflictError(
            "The mark scheme can only be edited while the exam is a draft", code="exam.not_draft"
        )
    report = validate_mark_scheme(scheme)
    if not report.can_save:
        raise ValidationFailedError(
            "The mark scheme has errors", code="mark_scheme.invalid", issues=report.blocking
        )

    before = scheme_of(exam).model_dump()
    exam.questions.clear()
    db.flush()  # delete old rows first so unique (exam, label/position) cannot clash
    for qi, q in enumerate(scheme.questions):
        exam.questions.append(
            Question(
                label=q.label,
                prompt_text=q.prompt_text,
                max_half_marks=to_half_marks(q.max_marks),
                position=qi,
                points=[
                    MarkSchemePoint(
                        description=p.description,
                        half_marks=to_half_marks(p.marks),
                        alternatives=list(p.alternatives),
                        position=pi,
                    )
                    for pi, p in enumerate(q.points)
                ],
            )
        )
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="replace_mark_scheme",
        old_value=before,
        new_value=scheme.model_dump(),
    )
    return exam, report


def set_status(db: Session, actor: User, exam_id: int, target: ExamStatus) -> Exam:
    exam = get_visible_exam(db, actor, exam_id)
    if exam.status == target:
        return exam
    if (exam.status, target) not in _ALLOWED_TRANSITIONS:
        raise ConflictError(
            f"Cannot change exam from {exam.status} to {target}", code="exam.invalid_transition"
        )
    if target == ExamStatus.DRAFT and has_uploads(db, exam.id):
        raise ConflictError(
            "Scans have been uploaded for this exam; it can no longer return to draft",
            code="exam.has_scripts",
        )
    if target == ExamStatus.READY:
        report = validation_of(exam)
        if not report.is_ready:
            raise ValidationFailedError(
                "The mark scheme is not complete",
                code="exam.not_ready",
                issues=report.blocking + report.readiness,
            )
    before = exam.status.value
    exam.status = target
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="set_status",
        old_value=before,
        new_value=target.value,
    )
    return exam


def delete_exam(db: Session, actor: User, exam_id: int) -> None:
    exam = get_visible_exam(db, actor, exam_id)
    if exam.status != ExamStatus.DRAFT:
        raise ConflictError("Only draft exams can be deleted", code="exam.not_draft")
    audit.record(
        db,
        actor=actor,
        entity_type="exam",
        entity_id=exam.id,
        action="delete",
        old_value={**_details(exam), "mark_scheme": scheme_of(exam).model_dump()},
    )
    db.delete(exam)
