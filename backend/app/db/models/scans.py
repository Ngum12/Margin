from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import utcnow
from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.db.models.classes import Student
from app.db.types import str_enum


class CoverSheet(IdMixin, Base):
    """One printable cover sheet per (exam, student). The QR code carries ``token``, never ids."""

    __tablename__ = "cover_sheet"
    __table_args__ = (UniqueConstraint("exam_id", "student_id"),)

    exam_id: Mapped[int] = mapped_column(ForeignKey("exam.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"))
    token: Mapped[str] = mapped_column(String(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    student: Mapped[Student] = relationship()


class UploadStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class Upload(IdMixin, Base):
    __tablename__ = "upload"
    __table_args__ = (UniqueConstraint("exam_id", "sha256"),)

    exam_id: Mapped[int] = mapped_column(ForeignKey("exam.id"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    original_filename: Mapped[str] = mapped_column(String(255))
    # Relative to MARGIN_DATA_DIR. The original PDF is kept byte-for-byte (D-030).
    stored_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[UploadStatus] = mapped_column(
        str_enum(UploadStatus, "upload_status"), default=UploadStatus.PENDING
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ScriptStatus(StrEnum):
    WAITING = "waiting"
    TRANSCRIBED = "transcribed"
    AI_MARKED = "ai_marked"
    IN_REVIEW = "in_review"
    CONFIRMED = "confirmed"


class Script(IdMixin, TimestampMixin, Base):
    __tablename__ = "script"
    __table_args__ = (UniqueConstraint("exam_id", "student_id"),)

    exam_id: Mapped[int] = mapped_column(ForeignKey("exam.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"))
    status: Mapped[ScriptStatus] = mapped_column(
        str_enum(ScriptStatus, "script_status"), default=ScriptStatus.WAITING
    )
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Set when the AI could not produce valid output: the teacher marks this script by hand.
    manual_reason: Mapped[str | None] = mapped_column(String(64))
    ai_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # First teacher edit during review.
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # AI marking run: 0 for the first, +1 for every re-run. Only the current run's mark
    # decisions are shown and used; earlier runs stay in the database as history.
    ai_run: Mapped[int] = mapped_column(Integer, default=0)
    # What the worker is doing now, for the live progress view (never part of the results):
    # "reading" page n of total, or "marking" question n of total; null when idle.
    ai_step: Mapped[str | None] = mapped_column(String(16))
    ai_step_index: Mapped[int | None] = mapped_column(Integer)
    ai_step_total: Mapped[int | None] = mapped_column(Integer)
    ai_step_page_id: Mapped[int | None] = mapped_column(Integer)
    ai_step_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    student: Mapped[Student] = relationship()
    pages: Mapped[list["Page"]] = relationship(
        back_populates="script", order_by="Page.position", foreign_keys="Page.script_id"
    )


class PageState(StrEnum):
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    DISCARDED = "discarded"


class UnassignedReason(StrEnum):
    """Why a page could not be placed automatically. Shown to teachers (translated)."""

    BEFORE_FIRST_COVER = "before_first_cover"
    FOLLOWS_UNASSIGNED_COVER = "follows_unassigned_cover"
    QR_DAMAGED = "qr_damaged"
    QR_UNREADABLE = "qr_unreadable"
    QR_CONFLICT = "qr_conflict"
    QR_NOT_OURS = "qr_not_ours"
    QR_BAD_CHECKSUM = "qr_bad_checksum"
    UNKNOWN_SHEET = "unknown_sheet"
    OTHER_EXAM = "other_exam"
    DUPLICATE_IN_UPLOAD = "duplicate_in_upload"
    ALREADY_UPLOADED = "already_uploaded"
    RETURNED_BY_TEACHER = "returned_by_teacher"


class Page(IdMixin, Base):
    __tablename__ = "page"
    __table_args__ = (UniqueConstraint("upload_id", "source_page_index"),)

    upload_id: Mapped[int] = mapped_column(ForeignKey("upload.id"), index=True)
    # 0-based index in the uploaded PDF.
    source_page_index: Mapped[int] = mapped_column(Integer)
    # Relative to MARGIN_DATA_DIR.
    image_path: Mapped[str] = mapped_column(String(500))
    thumb_path: Mapped[str] = mapped_column(String(500))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    # Orientation (Phase 4). All angles are clockwise degrees (0/90/180/270). The stored image
    # file is never changed; the effective rotation is applied when displaying and before
    # transcription. See effective_rotation and docs/DECISIONS.md D-049.
    # Already applied to the stored image by Phase 2 (legacy covers): never applied again.
    rotation_baked: Mapped[int] = mapped_column(Integer, default=0)
    # From the cover sheet's QR orientation, for the cover and the pages after it (layer b).
    rotation_stack: Mapped[int] = mapped_column(Integer, default=0)
    # From the Reader's orientation judgement before transcription (layer c).
    rotation_auto: Mapped[int] = mapped_column(Integer, default=0)
    auto_rotation_confidence: Mapped[float | None] = mapped_column(Float)
    auto_rotation_model: Mapped[str | None] = mapped_column(String(100))
    auto_rotation_prompt_version: Mapped[str | None] = mapped_column(String(100))
    # Set by a teacher with the rotate control (layer a); overrides the others when set.
    rotation_teacher: Mapped[int | None] = mapped_column(Integer)
    # The teacher rotated the page after it had been transcribed.
    rotated_after_transcription: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[PageState] = mapped_column(str_enum(PageState, "page_state"))
    script_id: Mapped[int | None] = mapped_column(ForeignKey("script.id"), index=True)
    # 1-based position within the script (cover sheet first).
    position: Mapped[int | None] = mapped_column(Integer)
    unassigned_reason: Mapped[UnassignedReason | None] = mapped_column(
        str_enum(UnassignedReason, "unassigned_reason")
    )
    # For pages that follow a problem cover: that cover page.
    related_page_id: Mapped[int | None] = mapped_column(ForeignKey("page.id"))
    # For "other_exam": the exam the sheet belongs to.
    detected_exam_id: Mapped[int | None] = mapped_column(ForeignKey("exam.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    upload: Mapped[Upload] = relationship()
    script: Mapped[Script | None] = relationship(back_populates="pages", foreign_keys=[script_id])

    @property
    def effective_rotation(self) -> int:
        """Clockwise degrees to turn the stored image so it reads upright."""
        if self.rotation_teacher is not None:
            return self.rotation_teacher % 360
        return (self.rotation_stack + self.rotation_auto) % 360

    @property
    def auto_rotated(self) -> bool:
        return self.rotation_teacher is None and self.rotation_auto % 360 != 0
