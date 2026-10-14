"""Mark scheme input as edited in the UI or parsed from CSV. Marks are whole marks here."""

from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel, LongText

Alternative = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
# Bounds checks on labels and marks are business rules (app.services.mark_scheme), reported as
# translated issues. These schema limits only stop absurd payloads.
Label = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class PointIn(ApiModel):
    description: LongText = ""
    marks: int = Field(ge=-1000, le=1000)
    alternatives: list[Alternative] = Field(default_factory=list, max_length=50)


class QuestionIn(ApiModel):
    label: Label
    prompt_text: LongText = ""
    max_marks: int = Field(ge=-1000, le=1000)
    points: list[PointIn] = Field(default_factory=list, max_length=200)


class MarkSchemeIn(ApiModel):
    questions: list[QuestionIn] = Field(default_factory=list, max_length=500)
