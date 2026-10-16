from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.db.models import Language, Role
from app.schemas.common import ApiModel, RequiredShortText

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",  # lower-cased after matching
    ),
]
Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]
Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
]


class LoginIn(ApiModel):
    # Lenient on purpose: any input gets the same generic "incorrect" answer.
    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=64)]
    password: Annotated[str, Field(max_length=MAX_PASSWORD_LENGTH)]


class UserOut(ApiModel):
    id: int
    username: str
    display_name: str
    email: str | None
    role: Role
    department_subject_codes: list[str]
    preferred_language: Language
    is_active: bool
    last_login_at: datetime | None


class SchoolOut(ApiModel):
    id: int
    name: str
    country: str
    curriculum: str


class MeOut(ApiModel):
    user: UserOut
    school: SchoolOut
    csrf_token: str


class LanguageIn(ApiModel):
    preferred_language: Language


class UserCreateIn(ApiModel):
    username: Username
    display_name: RequiredShortText
    email: Email | None = None
    password: Password
    department_subject_codes: list[RequiredShortText] = Field(default_factory=list, max_length=30)
    role: Role = Role.TEACHER
    preferred_language: Language = Language.EN


class UserUpdateIn(ApiModel):
    display_name: RequiredShortText | None = None
    email: Email | None = None
    department_subject_codes: list[RequiredShortText] | None = Field(default=None, max_length=30)
    role: Role | None = None
    preferred_language: Language | None = None
    is_active: bool | None = None


class PasswordResetIn(ApiModel):
    password: Password
