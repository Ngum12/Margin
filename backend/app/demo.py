"""Demo data: one teacher, six students, and Chemistry, Mathematics and Economics exams
whose mark schemes are ready and whose cover sheets are prepared. Everything goes through the
normal services, so it is audited like real work. Run once; it refuses to run twice."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExamStatus, Role, School, User
from app.schemas.accounts import UserCreateIn
from app.schemas.classes import ClassIn
from app.schemas.mark_scheme import MarkSchemeIn, PointGroup, PointIn, PointRules, QuestionIn
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


MATH_SCHEME = MarkSchemeIn(
    questions=[
        QuestionIn(
            label="1",
            prompt_text="Solve 2x + 3 = 7.",
            max_marks=2,
            points=[
                PointIn(
                    description="Subtracts 3 from both sides: 2x = 4",
                    marks=1,
                    rules=PointRules(key="M1", kind="M"),
                ),
                PointIn(
                    description="x = 2",
                    marks=1,
                    rules=PointRules(key="A1", kind="A", depends_on=["M1"]),
                ),
            ],
        )
    ]
)
ECONOMICS_SCHEME = MarkSchemeIn(
    questions=[
        QuestionIn(
            label="1(a)",
            prompt_text="Define opportunity cost.",
            max_marks=1,
            points=[
                PointIn(
                    description="The next best alternative forgone",
                    marks=1,
                    alternatives=["Value of the best alternative given up"],
                )
            ],
        ),
        QuestionIn(
            label="1(b)",
            prompt_text="State two factors that shift demand.",
            max_marks=2,
            groups=[PointGroup(key="any2", max_points=2, max_marks=2)],
            points=[
                PointIn(description=text, marks=1, rules=PointRules(group="any2"))
                for text in ["Consumer income", "Tastes and preferences", "Price of a related good"]
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
    first_exam = 0
    for subject, title, scheme in [
        ("chemistry", "Demo: Chemistry term test", DEMO_SCHEME),
        ("mathematics", "Demo: Mathematics term test", MATH_SCHEME),
        ("economics", "Demo: Economics term test", ECONOMICS_SCHEME),
    ]:
        exam = exams.create_exam(
            db, teacher, class_id=klass.id, subject_code=subject, title=title, exam_date=None
        )
        exam.term = "Demo term"
        db.flush()
        exams.replace_mark_scheme(db, teacher, exam.id, scheme)
        exams.set_status(db, teacher, exam.id, ExamStatus.READY)
        cover_sheets.prepare_sheets(db, teacher, exam.id)
        if not first_exam:
            first_exam = exam.id
    return teacher.username, first_exam
