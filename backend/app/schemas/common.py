from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.errors import Issue

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
RequiredShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class IssueOut(ApiModel):
    code: str
    path: list[str | int]
    params: dict[str, object]

    @classmethod
    def of(cls, issue: Issue) -> "IssueOut":
        return cls(code=issue.code, path=issue.path, params=issue.params)


class ErrorOut(ApiModel):
    code: str
    detail: str
    issues: list[IssueOut] = []
