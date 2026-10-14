"""All ORM models. Import from here so every table is registered on ``Base.metadata``."""

from app.db.models.accounts import Language, LoginAttempt, Role, School, User, UserSession
from app.db.models.audit import AuditEvent
from app.db.models.classes import SchoolClass, Student
from app.db.models.exams import Exam, ExamStatus, MarkSchemePoint, Question

__all__ = [
    "AuditEvent",
    "Exam",
    "ExamStatus",
    "Language",
    "LoginAttempt",
    "MarkSchemePoint",
    "Question",
    "Role",
    "School",
    "SchoolClass",
    "Student",
    "User",
    "UserSession",
]
