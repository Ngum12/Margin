"""Files produced for download (Phase 5): CSV, marked PDFs and training datasets."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.db.base import Base, IdMixin, UTCDateTime
from app.db.types import str_enum


class ExportKind(StrEnum):
    CSV = "csv"
    STUDENT_PDF = "student_pdf"
    CLASS_PDF = "class_pdf"
    DATASET = "dataset"


class ExportStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class Export(IdMixin, Base):
    __tablename__ = "export"

    kind: Mapped[ExportKind] = mapped_column(str_enum(ExportKind, "export_kind"))
    # Null for a training dataset, which can span several exams.
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exam.id"), index=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    status: Mapped[ExportStatus] = mapped_column(
        str_enum(ExportStatus, "export_status"), default=ExportStatus.PENDING
    )
    # Language of headings in the file ("en" or "fr").
    language: Mapped[str] = mapped_column(String(8), default="en")
    # Relative to MARGIN_DATA_DIR; served only through an authenticated endpoint.
    file_path: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
