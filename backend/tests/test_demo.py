import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import demo
from app.db.models import CoverSheet, Exam, ExamStatus, Student
from tests.conftest import World


def test_demo_seed_creates_a_ready_exam_with_cover_sheets(db: Session, world: World) -> None:
    username, exam_id = demo.seed_demo(db, "demo-password-123")
    db.commit()

    exam = db.get(Exam, exam_id)
    assert username == "demo"
    assert exam is not None
    assert exam.status == ExamStatus.READY
    assert (
        db.scalar(
            select(func.count()).select_from(Student).where(Student.class_id == exam.class_id)
        )
        == 6
    )
    assert db.scalar(select(func.count()).select_from(CoverSheet)) == 18
    assert set(db.scalars(select(Exam.subject_code))) == {"chemistry", "mathematics", "economics"}


def test_demo_seed_runs_only_once(db: Session, world: World) -> None:
    demo.seed_demo(db, "demo-password-123")
    db.commit()
    with pytest.raises(demo.DemoExistsError):
        demo.seed_demo(db, "demo-password-123")
