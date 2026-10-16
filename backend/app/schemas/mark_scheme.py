"""Mark scheme input as edited in the UI or parsed from CSV. Marks are whole marks here."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel, LongText

Alternative = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
# Bounds checks on labels and marks are business rules (app.services.mark_scheme), reported as
# translated issues. These schema limits only stop absurd payloads.
Label = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class PointRules(ApiModel):
    key: str = Field(default="", max_length=40, pattern=r"^[a-zA-Z0-9_-]*$")
    reject: list[Alternative] = Field(default_factory=list, max_length=50)
    kind: Literal["point", "M", "A", "B"] = "point"
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    ecf: bool = False
    ecf_from: str = Field(default="", max_length=200)
    meaning_based: bool = True
    teacher_only: bool = False
    group: str = Field(default="", max_length=40)


class PointGroup(ApiModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    max_points: int = Field(ge=1, le=50)
    max_marks: int = Field(ge=1, le=100)


class PointIn(ApiModel):
    rules: PointRules = Field(default_factory=PointRules)
    description: LongText = ""
    marks: int = Field(ge=-1000, le=1000)
    alternatives: list[Alternative] = Field(default_factory=list, max_length=50)


class QuestionIn(ApiModel):
    groups: list[PointGroup] = Field(default_factory=list, max_length=50)
    label: Label
    prompt_text: LongText = ""
    max_marks: int = Field(ge=-1000, le=1000)
    points: list[PointIn] = Field(default_factory=list, max_length=200)


class MarkSchemeIn(ApiModel):
    questions: list[QuestionIn] = Field(default_factory=list, max_length=500)
