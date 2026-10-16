"""School-local originals, extraction drafts and reusable confirmed schemes."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime


class SchemeDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "scheme_document"
    exam_id: Mapped[int] = mapped_column(ForeignKey("exam.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    suffix: Mapped[str] = mapped_column(String(10))
    file_path: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    text: Mapped[str] = mapped_column(Text, default="")
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(200))
    model_version: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(200))
    extracted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class SchemeLibrary(IdMixin, TimestampMixin, Base):
    __tablename__ = "scheme_library"
    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String(200))
    subject_code: Mapped[str] = mapped_column(String(50))
    scheme: Mapped[dict[str, Any]] = mapped_column(JSON)
