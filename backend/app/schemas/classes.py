from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel, ShortText

AcademicYear = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=20)]
ClassName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ClassIn(ApiModel):
    name: ClassName
    academic_year: AcademicYear
    teacher_id: int


class ClassUpdateIn(ApiModel):
    name: ClassName | None = None
    academic_year: AcademicYear | None = None
    teacher_id: int | None = None


class ClassOut(ApiModel):
    id: int
    name: str
    academic_year: str
    teacher_id: int
    teacher_name: str
    student_count: int


class StudentsCreateIn(ApiModel):
    """Add students to a class. Each entry is an optional display name (blank = code only)."""

    names: list[ShortText] = Field(min_length=1, max_length=300)


class StudentUpdateIn(ApiModel):
    display_name: ShortText | None = None
    class_id: int | None = None


class ConsentIn(ApiModel):
    training_consent: bool


class StudentOut(ApiModel):
    is_active: bool
    register_position: int
    id: int
    class_id: int
    code: str
    display_name: str | None
    training_consent: bool
    consent_recorded_at: datetime | None
    consent_recorded_by_id: int | None
