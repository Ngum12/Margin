"""School-local intake and printing. Hardware side effects have durable receipts."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.db.base import Base, IdMixin, UTCDateTime


class Hardware(IdMixin, Base):
    __tablename__ = "hardware"

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), unique=True)
    inbox_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    printer_uri: Mapped[str] = mapped_column(String(500), default="")
    duplex: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    test_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ExamAbsence(IdMixin, Base):
    __tablename__ = "exam_absence"
    __table_args__ = (UniqueConstraint("exam_id", "student_id"),)

    exam_id: Mapped[int] = mapped_column(ForeignKey("exam.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"))
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ScanBatch(IdMixin, Base):
    __tablename__ = "scan_batch"
    __table_args__ = (UniqueConstraint("school_id", "sha256"),)

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    captured_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    capture_options: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    prepared_path: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    source_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class IntakePage(IdMixin, Base):
    __tablename__ = "intake_page"
    __table_args__ = (UniqueConstraint("batch_id", "source_index"),)

    answer_sheet_id: Mapped[int | None] = mapped_column(ForeignKey("answer_sheet.id"))
    suggested_student_id: Mapped[int | None] = mapped_column(ForeignKey("student.id"))
    identification_model: Mapped[str | None] = mapped_column(String(100))
    batch_id: Mapped[int] = mapped_column(ForeignKey("scan_batch.id"), index=True)
    source_index: Mapped[int] = mapped_column(Integer)
    image_path: Mapped[str] = mapped_column(String(500))
    thumb_path: Mapped[str] = mapped_column(String(500))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(String(100))
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exam.id"))
    page_id: Mapped[int | None] = mapped_column(ForeignKey("page.id"))
    discarded: Mapped[bool] = mapped_column(Boolean, default=False)


class PrintJob(IdMixin, Base):
    __tablename__ = "print_job"

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exam.id"))
    # The unique request token prevents double clicks/retried HTTP requests printing twice.
    request_key: Mapped[str] = mapped_column(String(100), unique=True)
    script_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    confirmation_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    kind: Mapped[str] = mapped_column(String(30), default="feedback")
    language: Mapped[str] = mapped_column(String(2), default="en")
    status: Mapped[str] = mapped_column(String(30), default="queued")
    printer_uri: Mapped[str] = mapped_column(String(500))
    duplex: Mapped[bool] = mapped_column(Boolean)
    printer_job_id: Mapped[int | None] = mapped_column(Integer)
    file_path: Mapped[str | None] = mapped_column(String(500))
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
