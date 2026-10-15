from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.db.base import Base, IdMixin, UTCDateTime
from app.db.types import str_enum


class JobType(StrEnum):
    PROCESS_UPLOAD = "process_upload"
    TRANSCRIBE_SCRIPT = "transcribe_script"
    MARK_SCRIPT = "mark_script"
    # A teacher asked for a fresh read of one page after correcting its orientation (Phase 4).
    TRANSCRIBE_PAGE = "transcribe_page"
    # Phase 5: files built in the background.
    EXPORT_PDFS = "export_pdfs"
    EXPORT_DATASET = "export_dataset"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(IdMixin, Base):
    """Durable unit of background work. Payloads hold ids only, never student content."""

    __tablename__ = "job"

    type: Mapped[JobType] = mapped_column(str_enum(JobType, "job_type"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus, "job_status"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_after: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    locked_by: Mapped[str | None] = mapped_column(String(100))
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Error code and exception type only; never page content or transcriptions.
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class WorkerHeartbeat(IdMixin, Base):
    """Lets the web app tell teachers whether the background worker is running."""

    __tablename__ = "worker_heartbeat"

    worker_id: Mapped[str] = mapped_column(String(100), unique=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    seen_at: Mapped[datetime] = mapped_column(UTCDateTime())


class ModelRole(StrEnum):
    READER = "reader"
    MARKER = "marker"


class ModelVersion(IdMixin, Base):
    __tablename__ = "model_version"
    __table_args__ = (UniqueConstraint("name", "version", "role"),)

    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    role: Mapped[ModelRole] = mapped_column(str_enum(ModelRole, "model_role"))
    # "ollama", "mock", later "fine-tuned"
    source: Mapped[str] = mapped_column(String(50))
    installed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text)


class TranscriptionSource(StrEnum):
    MODEL = "model"
    TEACHER = "teacher"


class Transcription(IdMixin, Base):
    """One version of one page's text. Never overwritten; newer rows supersede older ones."""

    __tablename__ = "transcription"
    __table_args__ = (
        UniqueConstraint(
            "page_id", "source", "model_name", "model_version", "prompt_version", "rotation"
        ),
    )

    script_id: Mapped[int] = mapped_column(ForeignKey("script.id"), index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("page.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[TranscriptionSource] = mapped_column(
        str_enum(TranscriptionSource, "transcription_source")
    )
    # Set for model output (null for teacher edits).
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # Clockwise degrees the page was turned when the model read it (Phase 4). A teacher can ask
    # for a fresh read after correcting the orientation; it is stored beside the first read.
    rotation: Mapped[int] = mapped_column(Integer, default=0)


class ErrorCategory(StrEnum):
    CORRECT = "correct"
    CONCEPTUAL_ERROR = "conceptual_error"
    LANGUAGE_EXPRESSION = "language_expression"
    TRANSCRIPTION_UNCERTAIN = "transcription_uncertain"
    OMITTED = "omitted"


class MarkDecision(IdMixin, Base):
    """The model's proposal for one mark scheme point, and later the teacher's final decision."""

    __tablename__ = "mark_decision"
    __table_args__ = (
        UniqueConstraint(
            "script_id", "mark_scheme_point_id", "model_name", "model_version", "prompt_version"
        ),
    )

    script_id: Mapped[int] = mapped_column(ForeignKey("script.id"), index=True)
    mark_scheme_point_id: Mapped[int] = mapped_column(ForeignKey("mark_scheme_point.id"))
    # The AI's proposal, in half-mark units (D-018). All proposal fields are empty for points a
    # teacher marks without an AI proposal (scripts flagged for manual marking).
    proposed_half_marks: Mapped[int | None] = mapped_column(Integer)
    evidence: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float)
    error_category: Mapped[ErrorCategory | None] = mapped_column(
        str_enum(ErrorCategory, "error_category")
    )
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    proposed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=utcnow)
    # Teacher's decision (Phase 4). Null until decided.
    final_half_marks: Mapped[int | None] = mapped_column(Integer)
    final_category: Mapped[ErrorCategory | None] = mapped_column(
        str_enum(ErrorCategory, "final_error_category")
    )
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class QuestionComment(IdMixin, Base):
    """A teacher's short comment on one question of one script."""

    __tablename__ = "question_comment"
    __table_args__ = (UniqueConstraint("script_id", "question_id"),)

    script_id: Mapped[int] = mapped_column(ForeignKey("script.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("question.id"))
    text: Mapped[str] = mapped_column(String(300))
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ReviewSession(IdMixin, Base):
    """Time a teacher spends reviewing a script (owner change 2, Phase 4). Local data only."""

    __tablename__ = "review_session"

    script_id: Mapped[int] = mapped_column(ForeignKey("script.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime())
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Seconds the review screen was visible and in use (idle gaps over 5 minutes excluded).
    active_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
