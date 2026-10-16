from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class RosterImport(IdMixin, TimestampMixin, Base):
    __tablename__ = "roster_import"
    class_id: Mapped[int] = mapped_column(ForeignKey("school_class.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    file_path: Mapped[str] = mapped_column(String(500))
    suffix: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text, default="")
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
