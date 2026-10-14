from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import SchoolClass, Student, User
from app.errors import ConflictError, Issue, ValidationFailedError
from app.schemas.classes import ClassIn, ClassUpdateIn
from app.services import audit
from app.services.access import get_visible_class, require_admin, visible_classes


def _snapshot(school_class: SchoolClass) -> dict[str, object]:
    return {
        "name": school_class.name,
        "academic_year": school_class.academic_year,
        "teacher_id": school_class.teacher_id,
    }


def student_counts(db: Session, class_ids: list[int]) -> dict[int, int]:
    if not class_ids:
        return {}
    rows = db.execute(
        select(Student.class_id, func.count())
        .where(Student.class_id.in_(class_ids))
        .group_by(Student.class_id)
    )
    return dict(rows.all())


def list_classes(db: Session, actor: User) -> list[SchoolClass]:
    return list(
        db.scalars(
            visible_classes(actor).order_by(SchoolClass.academic_year.desc(), SchoolClass.name)
        )
    )


def _check_teacher(db: Session, actor: User, teacher_id: int) -> None:
    teacher = db.get(User, teacher_id)
    if teacher is None or teacher.school_id != actor.school_id or not teacher.is_active:
        raise ValidationFailedError(
            "Teacher must be an active user of this school",
            code="class.teacher_invalid",
            issues=[Issue("class.teacher_invalid", ["teacher_id"])],
        )


def _flush_unique(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "A class with this name already exists for that year", code="class.duplicate"
        ) from exc


def create_class(db: Session, actor: User, data: ClassIn) -> SchoolClass:
    require_admin(actor)
    _check_teacher(db, actor, data.teacher_id)
    school_class = SchoolClass(school_id=actor.school_id, **data.model_dump())
    db.add(school_class)
    _flush_unique(db)
    audit.record(
        db,
        actor=actor,
        entity_type="class",
        entity_id=school_class.id,
        action="create",
        new_value=_snapshot(school_class),
    )
    return school_class


def update_class(db: Session, actor: User, class_id: int, data: ClassUpdateIn) -> SchoolClass:
    require_admin(actor)
    school_class = get_visible_class(db, actor, class_id)
    before = _snapshot(school_class)
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if "teacher_id" in changes:
        _check_teacher(db, actor, changes["teacher_id"])
    for field, value in changes.items():
        setattr(school_class, field, value)
    _flush_unique(db)
    after = _snapshot(school_class)
    if after != before:
        audit.record(
            db,
            actor=actor,
            entity_type="class",
            entity_id=school_class.id,
            action="update",
            old_value=before,
            new_value=after,
        )
    return school_class
