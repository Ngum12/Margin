"""Student authentication is independent of staff users and staff sessions."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import utcnow
from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.db.models.classes import Student


class StudentAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "student_account"
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"), unique=True)
    pin_hash: Mapped[str] = mapped_column(String(255))
    must_change_pin: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    pin_changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    student: Mapped[Student] = relationship()


class StudentSession(IdMixin, Base):
    __tablename__ = "student_session"
    account_id: Mapped[int] = mapped_column(ForeignKey("student_account.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    account: Mapped[StudentAccount] = relationship()


class StudentLoginAttempt(IdMixin, Base):
    __tablename__ = "student_login_attempt"
    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    client_ip: Mapped[str] = mapped_column(String(64), index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean)
    attempted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


class RemarkRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "remark_request"
    __table_args__ = (UniqueConstraint("script_id", "question_id"),)
    script_id: Mapped[int] = mapped_column(ForeignKey("script.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("question.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"), index=True)
    reason: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500))
    page_id: Mapped[int | None] = mapped_column(ForeignKey("page.id"))
    location: Mapped[dict[str, float] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    escalated_once: Mapped[bool] = mapped_column(Boolean, default=False)
    awaiting_hod: Mapped[bool] = mapped_column(Boolean, default=False)
    responses: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    student_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
