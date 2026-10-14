"""All ORM models. Import from here so every table is registered on ``Base.metadata``."""

from app.db.models.accounts import Language, LoginAttempt, Role, School, User, UserSession
from app.db.models.audit import AuditEvent
from app.db.models.classes import SchoolClass, Student
from app.db.models.exams import Exam, ExamStatus, MarkSchemePoint, Question
from app.db.models.scans import (
    CoverSheet,
    Page,
    PageState,
    Script,
    ScriptStatus,
    UnassignedReason,
    Upload,
    UploadStatus,
)

__all__ = [
    "AuditEvent",
    "CoverSheet",
    "Exam",
    "ExamStatus",
    "Language",
    "LoginAttempt",
    "MarkSchemePoint",
    "Page",
    "PageState",
    "Question",
    "Role",
    "School",
    "SchoolClass",
    "Script",
    "ScriptStatus",
    "Student",
    "UnassignedReason",
    "Upload",
    "UploadStatus",
    "User",
    "UserSession",
]
