"""All ORM models. Import from here so every table is registered on ``Base.metadata``."""

from app.db.models.accounts import Language, LoginAttempt, Role, School, User, UserSession
from app.db.models.ai import (
    ErrorCategory,
    Job,
    JobStatus,
    JobType,
    MarkDecision,
    ModelRole,
    ModelVersion,
    QuestionComment,
    ReviewSession,
    Transcription,
    TranscriptionSource,
    WorkerHeartbeat,
)
from app.db.models.audit import AuditEvent
from app.db.models.classes import SchoolClass, Student
from app.db.models.exams import Exam, ExamStatus, MarkSchemePoint, Question
from app.db.models.exports import Export, ExportKind, ExportStatus
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
    "ErrorCategory",
    "Exam",
    "ExamStatus",
    "Export",
    "ExportKind",
    "ExportStatus",
    "Job",
    "JobStatus",
    "JobType",
    "Language",
    "LoginAttempt",
    "MarkDecision",
    "MarkSchemePoint",
    "ModelRole",
    "ModelVersion",
    "Page",
    "PageState",
    "Question",
    "QuestionComment",
    "ReviewSession",
    "Role",
    "School",
    "SchoolClass",
    "Script",
    "ScriptStatus",
    "Student",
    "Transcription",
    "TranscriptionSource",
    "UnassignedReason",
    "Upload",
    "UploadStatus",
    "User",
    "UserSession",
    "WorkerHeartbeat",
]
