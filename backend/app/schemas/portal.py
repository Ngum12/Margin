from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel

Pin = Annotated[str, StringConstraints(pattern=r"^[0-9]{6,12}$")]


class PortalSettings(ApiModel):
    enabled: bool = False
    remark_days: int = Field(default=7, ge=1, le=90)
    remark_max: int = Field(default=3, ge=1, le=20)
    escalation: bool = False
    class_average: bool = False
    idle_minutes: int = Field(default=10, ge=2, le=30)


class StudentLogin(ApiModel):
    school_id: int
    code: str = Field(max_length=16)
    pin: str = Field(max_length=128)


class ChangePin(ApiModel):
    old_pin: str = Field(max_length=128)
    pin: Pin


class ReleaseIn(ApiModel):
    released: bool
    visibility: Literal["marks", "notes", "scheme"] = "notes"


class RemarkIn(ApiModel):
    question_id: int
    reason: Literal["missing_mark", "total_error", "unmarked_answer", "other"]
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    page_id: int | None = None
    x: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    y: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class RemarkReply(ApiModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    # Per-point marks, so dependencies and any-N groups still apply.
    marks: dict[int, int] = Field(default_factory=dict, max_length=100)


class CredentialIn(ApiModel):
    student_ids: list[int] = Field(min_length=1, max_length=200)
    reset: bool = False
    key: str = Field(min_length=16, max_length=100)
