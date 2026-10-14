"""Who can see what. Every query for classes, students and exams goes through these scopes.

- Admins see everything in their school.
- Teachers see only classes they teach, and the students and exams in those classes.
- Anything outside the actor's scope is reported as "not found", so ids cannot be probed.
"""

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Exam, SchoolClass, Student, User
from app.errors import NotFoundError, PermissionDeniedError


def require_admin(actor: User) -> None:
    if not actor.is_admin:
        raise PermissionDeniedError("Administrator access required", code="auth.admin_required")


def visible_classes(actor: User) -> Select[SchoolClass]:
    query = select(SchoolClass).where(SchoolClass.school_id == actor.school_id)
    if not actor.is_admin:
        query = query.where(SchoolClass.teacher_id == actor.id)
    return query


def visible_exams(actor: User) -> Select[Exam]:
    query = (
        select(Exam)
        .join(SchoolClass, Exam.class_id == SchoolClass.id)
        .where(SchoolClass.school_id == actor.school_id)
    )
    if not actor.is_admin:
        query = query.where(SchoolClass.teacher_id == actor.id)
    return query


def visible_students(actor: User) -> Select[Student]:
    query = (
        select(Student)
        .join(SchoolClass, Student.class_id == SchoolClass.id)
        .where(Student.school_id == actor.school_id)
    )
    if not actor.is_admin:
        query = query.where(SchoolClass.teacher_id == actor.id)
    return query


def get_visible_class(db: Session, actor: User, class_id: int) -> SchoolClass:
    school_class = db.scalar(visible_classes(actor).where(SchoolClass.id == class_id))
    if school_class is None:
        raise NotFoundError("Class")
    return school_class


def get_visible_exam(db: Session, actor: User, exam_id: int) -> Exam:
    exam = db.scalar(visible_exams(actor).where(Exam.id == exam_id))
    if exam is None:
        raise NotFoundError("Exam")
    return exam


def get_visible_student(db: Session, actor: User, student_id: int) -> Student:
    student = db.scalar(visible_students(actor).where(Student.id == student_id))
    if student is None:
        raise NotFoundError("Student")
    return student
