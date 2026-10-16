from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.db.base import Base, IdMixin, UTCDateTime


class AnswerSheet(IdMixin, Base):
    """One random token per physical page; spare tokens have no student until confirmed."""

    __tablename__ = "answer_sheet"

    exam_id: Mapped[int] = mapped_column(ForeignKey("exam.id"), index=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("student.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    layout: Mapped[str] = mapped_column(String(16), default="answer")
    token: Mapped[str] = mapped_column(String(32), unique=True)
    spare: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
