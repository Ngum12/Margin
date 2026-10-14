"""Students are identified by pseudonymous codes. Real names are optional and local-only."""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db.models import Student, User
from app.services import audit
from app.services.access import (
    get_visible_class,
    get_visible_student,
    require_admin,
    visible_students,
)

# No 0/O, 1/I/L: codes are read and typed from paper.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def generate_codes(db: Session, school_id: int, count: int) -> list[str]:
    existing = set(db.scalars(select(Student.code).where(Student.school_id == school_id)))
    codes: list[str] = []
    while len(codes) < count:
        code = _new_code()
        if code not in existing:
            existing.add(code)
            codes.append(code)
    return codes


def _snapshot(student: Student) -> dict[str, object]:
    # Names are deliberately not copied into the audit log; record only that one exists.
    return {
        "code": student.code,
        "class_id": student.class_id,
        "has_display_name": bool(student.display_name),
        "training_consent": student.training_consent,
    }


def list_students(db: Session, actor: User, class_id: int) -> list[Student]:
    get_visible_class(db, actor, class_id)
    return list(
        db.scalars(
            visible_students(actor).where(Student.class_id == class_id).order_by(Student.code)
        )
    )


def add_students(db: Session, actor: User, class_id: int, names: list[str]) -> list[Student]:
    require_admin(actor)
    school_class = get_visible_class(db, actor, class_id)
    codes = generate_codes(db, actor.school_id, len(names))
    students = [
        Student(
            school_id=actor.school_id,
            class_id=school_class.id,
            code=code,
            display_name=name or None,
            training_consent=False,
        )
        for code, name in zip(codes, names, strict=True)
    ]
    db.add_all(students)
    db.flush()
    for student in students:
        audit.record(
            db,
            actor=actor,
            entity_type="student",
            entity_id=student.id,
            action="create",
            new_value=_snapshot(student),
        )
    return students


def update_student(
    db: Session,
    actor: User,
    student_id: int,
    *,
    display_name: str | None,
    class_id: int | None,
    display_name_set: bool,
) -> Student:
    require_admin(actor)
    student = get_visible_student(db, actor, student_id)
    before = _snapshot(student)
    if display_name_set:
        student.display_name = display_name or None
    if class_id is not None:
        student.class_id = get_visible_class(db, actor, class_id).id
    after = _snapshot(student)
    if after != before or display_name_set:
        audit.record(
            db,
            actor=actor,
            entity_type="student",
            entity_id=student.id,
            action="update",
            old_value=before,
            new_value=after,
        )
    return student


def set_training_consent(db: Session, actor: User, student_id: int, consent: bool) -> Student:
    require_admin(actor)
    student = get_visible_student(db, actor, student_id)
    if student.training_consent == consent:
        return student
    before = _snapshot(student)
    student.training_consent = consent
    student.consent_recorded_at = utcnow()
    student.consent_recorded_by_id = actor.id
    audit.record(
        db,
        actor=actor,
        entity_type="student",
        entity_id=student.id,
        action="set_training_consent",
        old_value=before,
        new_value=_snapshot(student),
    )
    return student
