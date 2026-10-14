"""Domain errors raised by services and turned into JSON responses by the API layer.

Every error carries a stable ``code`` that the frontend translates (English and French), plus
an English ``message`` for logs and API users. Codes are part of the API contract.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Issue:
    """One validation problem. ``path`` locates it, e.g. ``["questions", 0, "points", 1]``."""

    code: str
    path: list[str | int] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


class DomainError(Exception):
    status_code = 400
    default_code = "error"

    def __init__(
        self, message: str, *, code: str | None = None, issues: list[Issue] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.issues = issues or []


class NotFoundError(DomainError):
    """Also used when the actor may not see the entity, so ids cannot be probed."""

    status_code = 404
    default_code = "not_found"

    def __init__(self, entity: str = "Resource") -> None:
        super().__init__(f"{entity} not found")


class PermissionDeniedError(DomainError):
    status_code = 403
    default_code = "forbidden"


class AuthenticationError(DomainError):
    status_code = 401
    default_code = "auth.required"


class TooManyAttemptsError(DomainError):
    status_code = 429
    default_code = "auth.too_many_attempts"


class ConflictError(DomainError):
    status_code = 409
    default_code = "conflict"


class ValidationFailedError(DomainError):
    status_code = 422
    default_code = "validation_failed"
