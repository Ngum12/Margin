import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Student
from app.services.students import CODE_ALPHABET, CODE_LENGTH, generate_codes
from tests.conftest import World
from tests.factories import ApiUser, Factory


@pytest.fixture
def admin(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "admin")


def test_admin_creates_class_for_a_teacher(admin: ApiUser, world: World) -> None:
    response = admin.post(
        "/api/classes",
        json={"name": "Form 4", "academic_year": "2026/2027", "teacher_id": world.teacher_a.id},
    )

    assert response.status_code == 201
    assert response.json()["teacher_name"] == "Alice"
    assert response.json()["student_count"] == 0


def test_duplicate_class_name_in_same_year_conflicts(admin: ApiUser, world: World) -> None:
    response = admin.post(
        "/api/classes",
        json={"name": "Form 5A", "academic_year": "2026/2027", "teacher_id": world.teacher_a.id},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "class.duplicate"


def test_class_teacher_must_be_an_active_user(
    admin: ApiUser, world: World, factory: Factory
) -> None:
    inactive = factory.user(world.school, "gone", active=False)

    response = admin.post(
        "/api/classes",
        json={"name": "Form 3", "academic_year": "2026/2027", "teacher_id": inactive.id},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "class.teacher_invalid"


def test_adding_students_generates_unique_readable_codes(admin: ApiUser, world: World) -> None:
    response = admin.post(
        f"/api/classes/{world.class_a.id}/students", json={"names": ["Ama Fon", "", "Bih"]}
    )

    assert response.status_code == 201
    students = response.json()
    codes = [s["code"] for s in students]
    assert len(set(codes)) == 3
    assert all(len(c) == CODE_LENGTH and set(c) <= set(CODE_ALPHABET) for c in codes)
    assert [s["display_name"] for s in students] == ["Ama Fon", None, "Bih"]
    assert all(s["training_consent"] is False for s in students)


def test_generated_codes_avoid_existing_ones(db: Session, world: World, factory: Factory) -> None:
    factory.student(world.class_a, "AAAAAA")

    codes = generate_codes(db, world.school.id, 200)

    assert "AAAAAA" not in codes
    assert len(set(codes)) == 200


def test_consent_records_who_and_when(
    admin: ApiUser, world: World, factory: Factory, db: Session
) -> None:
    student = factory.student(world.class_a, "AAAAAA")

    response = admin.put(f"/api/students/{student.id}/consent", json={"training_consent": True})

    body = response.json()
    assert body["training_consent"] is True
    assert body["consent_recorded_by_id"] == world.admin.id
    assert body["consent_recorded_at"] is not None
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "set_training_consent")).one()
    assert event.old_value["training_consent"] is False
    assert event.new_value["training_consent"] is True


def test_withdrawing_consent_is_recorded_too(
    admin: ApiUser, world: World, factory: Factory
) -> None:
    student = factory.student(world.class_a, "AAAAAA")
    admin.put(f"/api/students/{student.id}/consent", json={"training_consent": True})

    body = admin.put(f"/api/students/{student.id}/consent", json={"training_consent": False}).json()

    assert body["training_consent"] is False
    assert body["consent_recorded_at"] is not None


def test_student_names_never_reach_the_audit_log(admin: ApiUser, world: World, db: Session) -> None:
    created = admin.post(
        f"/api/classes/{world.class_a.id}/students", json={"names": ["Secret Name"]}
    ).json()
    admin.patch(f"/api/students/{created[0]['id']}", json={"display_name": "Other Secret"})

    dump = str([(e.old_value, e.new_value) for e in db.scalars(select(AuditEvent))])
    assert "Secret" not in dump


def test_student_can_be_moved_and_renamed(
    admin: ApiUser, world: World, factory: Factory, db: Session
) -> None:
    student = factory.student(world.class_a, "AAAAAA", "Old")

    response = admin.patch(
        f"/api/students/{student.id}", json={"display_name": "", "class_id": world.class_b.id}
    )

    assert response.json()["class_id"] == world.class_b.id
    assert response.json()["display_name"] is None
    db.expire_all()
    assert db.scalars(select(Student.class_id)).one() == world.class_b.id


def test_class_list_includes_student_counts(admin: ApiUser, world: World, factory: Factory) -> None:
    factory.student(world.class_a, "AAAAAA")
    factory.student(world.class_a, "BBBBBB")

    counts = {c["id"]: c["student_count"] for c in admin.get("/api/classes").json()}

    assert counts == {world.class_a.id: 2, world.class_b.id: 0}
