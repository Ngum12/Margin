"""Demo data for showing Margin (Phase 6): a teacher, a class of six students and a chemistry exam
whose mark scheme is ready and whose cover sheets are prepared. Everything goes through the
normal services, so it is audited like real work. Run once; it refuses to run twice."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExamStatus, Role, School, User
from app.schemas.accounts import UserCreateIn
from app.schemas.classes import ClassIn
from app.schemas.mark_scheme import MarkSchemeIn, PointIn, QuestionIn
from app.services import classes, cover_sheets, exams, students
from app.services.users import create_user_unchecked

DEMO_TEACHER = "demo"
DEMO_STUDENTS = [
    "Ama Fon",
    "Bih Ndi",
    "Che Nkeng",
    "Divine Tabe",
    "Esther Mbah",
    "Franck Ewane",
]
DEMO_SCHEME = MarkSchemeIn(
    questions=[
        QuestionIn(
            label="1(a)",
            prompt_text="State two properties of metals.",
            max_marks=2,
            points=[
                PointIn(description="Conducts electricity", marks=1, alternatives=["conductor"]),
                PointIn(description="Malleable", marks=1, alternatives=["can be hammered"]),
            ],
        ),
        QuestionIn(
            label="1(b)",
            prompt_text="Name the gas produced when zinc reacts with dilute acid.",
            max_marks=1,
            points=[PointIn(description="Hydrogen (H_2)", marks=1)],
        ),
        QuestionIn(
            label="2",
            prompt_text="Calculate the number of moles in 4.0 g of NaOH (Mr = 40).",
            max_marks=3,
            points=[
                PointIn(description="Uses moles = mass / Mr", marks=1),
                PointIn(description="Substitutes 4.0 / 40", marks=1),
                PointIn(description="Answer 0.1 mol", marks=1),
            ],
        ),
    ]
)


class DemoExistsError(Exception):
    pass


def seed_demo(db: Session, password: str) -> tuple[str, int]:
    """Create the demo data; return the teacher's username and the exam id."""
    school = db.scalar(select(School))
    if school is None:
        raise LookupError("Create the school first: python -m app.cli init-school ...")
    if db.scalar(select(User).where(User.username == DEMO_TEACHER)) is not None:
        raise DemoExistsError("The demo data already exists (user 'demo').")
    admin = db.scalar(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True)))
    if admin is None:
        raise LookupError("Create an administrator first: python -m app.cli create-user ...")
    teacher = create_user_unchecked(
        db,
        admin,
        school.id,
        UserCreateIn(
            username=DEMO_TEACHER,
            display_name="Demo Teacher",
            password=password,
            role=Role.TEACHER,
        ),
    )
    db.flush()
    klass = classes.create_class(
        db, admin, ClassIn(name="Form 5 Demo", academic_year="2026/2027", teacher_id=teacher.id)
    )
    db.flush()
    students.add_students(db, admin, klass.id, DEMO_STUDENTS)
    exam = exams.create_exam(
        db,
        teacher,
        class_id=klass.id,
        subject_code="chemistry",
        title="Demo: Chemistry term test",
        exam_date=None,
    )
    db.flush()
    exams.replace_mark_scheme(db, teacher, exam.id, DEMO_SCHEME)
    exams.set_status(db, teacher, exam.id, ExamStatus.READY)
    cover_sheets.prepare_sheets(db, teacher, exam.id)
    return teacher.username, exam.id
