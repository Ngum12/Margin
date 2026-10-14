from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.db.models import SchoolClass, Student
from app.schemas.classes import (
    ClassIn,
    ClassOut,
    ClassUpdateIn,
    ConsentIn,
    StudentOut,
    StudentsCreateIn,
    StudentUpdateIn,
)
from app.services import classes as class_service
from app.services import students as student_service

router = APIRouter(tags=["classes"])


def _class_out(school_class: SchoolClass, student_count: int) -> ClassOut:
    return ClassOut(
        id=school_class.id,
        name=school_class.name,
        academic_year=school_class.academic_year,
        teacher_id=school_class.teacher_id,
        teacher_name=school_class.teacher.display_name,
        student_count=student_count,
    )


@router.get("/classes")
def list_classes(db: DbSession, user: CurrentUser) -> list[ClassOut]:
    classes = class_service.list_classes(db, user)
    counts = class_service.student_counts(db, [c.id for c in classes])
    return [_class_out(c, counts.get(c.id, 0)) for c in classes]


@router.post("/classes", status_code=201)
def create_class(data: ClassIn, db: DbSession, user: CurrentUser) -> ClassOut:
    return _class_out(class_service.create_class(db, user, data), 0)


@router.patch("/classes/{class_id}")
def update_class(class_id: int, data: ClassUpdateIn, db: DbSession, user: CurrentUser) -> ClassOut:
    school_class = class_service.update_class(db, user, class_id, data)
    count = class_service.student_counts(db, [school_class.id]).get(school_class.id, 0)
    return _class_out(school_class, count)


@router.get("/classes/{class_id}/students")
def list_students(class_id: int, db: DbSession, user: CurrentUser) -> list[StudentOut]:
    return [StudentOut.model_validate(s) for s in student_service.list_students(db, user, class_id)]


@router.post("/classes/{class_id}/students", status_code=201)
def add_students(
    class_id: int, data: StudentsCreateIn, db: DbSession, user: CurrentUser
) -> list[StudentOut]:
    students: list[Student] = student_service.add_students(db, user, class_id, data.names)
    return [StudentOut.model_validate(s) for s in students]


@router.patch("/students/{student_id}")
def update_student(
    student_id: int, data: StudentUpdateIn, db: DbSession, user: CurrentUser
) -> StudentOut:
    student = student_service.update_student(
        db,
        user,
        student_id,
        display_name=data.display_name,
        class_id=data.class_id,
        display_name_set="display_name" in data.model_fields_set,
    )
    return StudentOut.model_validate(student)


@router.put("/students/{student_id}/consent")
def set_consent(student_id: int, data: ConsentIn, db: DbSession, user: CurrentUser) -> StudentOut:
    student = student_service.set_training_consent(db, user, student_id, data.training_consent)
    return StudentOut.model_validate(student)
