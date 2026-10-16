"""All ORM models. Import from here so every table is registered on ``Base.metadata``."""

from app.db.models.accounts import Language, LoginAttempt, Role, School, User, UserSession
from app.db.models.ai import (
    ErrorCategory,
    Job,
    JobStatus,
    JobType,
    MarkDecision,
    ModelCall,
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
from app.db.models.hardware import ExamAbsence, Hardware, IntakePage, PrintJob, ScanBatch
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
    "ExamAbsence",
    "ExamStatus",
    "Export",
    "ExportKind",
    "ExportStatus",
    "Hardware",
    "IntakePage",
    "Job",
    "JobStatus",
    "JobType",
    "Language",
    "LoginAttempt",
    "MarkDecision",
    "MarkSchemePoint",
    "ModelCall",
    "ModelRole",
    "ModelVersion",
    "Page",
    "PageState",
    "PrintJob",
    "Question",
    "QuestionComment",
    "ReviewSession",
    "Role",
    "ScanBatch",
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
