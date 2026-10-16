from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel


class RosterRow(ApiModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    code: Annotated[
        str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z0-9]{0,16}$")
    ] = ""


class RosterRows(ApiModel):
    rows: list[RosterRow] = Field(min_length=1, max_length=300)


class RegisterUpdate(ApiModel):
    student_ids: list[int] = Field(min_length=1, max_length=300)


class ActiveIn(ApiModel):
    active: bool
