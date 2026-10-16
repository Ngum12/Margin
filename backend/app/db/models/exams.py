from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.db.models.classes import SchoolClass
from app.db.types import str_enum


class ExamStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    MARKING = "marking"
    REVIEWING = "reviewing"
    COMPLETED = "completed"


class Exam(IdMixin, TimestampMixin, Base):
    __tablename__ = "exam"

    class_id: Mapped[int] = mapped_column(ForeignKey("school_class.id"), index=True)
    # References a subject config file (app/subjects/configs), not a table. See D-017.
    subject_code: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    exam_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ExamStatus] = mapped_column(
        str_enum(ExamStatus, "exam_status"), default=ExamStatus.DRAFT
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    # A teacher checked page orientation (owner, 2026-10-15). AI marking needs it; an upload
    # that adds pages clears it.
    pages_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    pages_checked_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    # Show the mark scheme to students (owner, 2026-10-15): prints "Missing:" notes for points
    # not earned on marked scripts and offers "Suggest from the mark scheme". Off by default.
    auto_start_marking: Mapped[bool] = mapped_column(Boolean, default=True)
    show_scheme_to_students: Mapped[bool] = mapped_column(Boolean, default=False)

    school_class: Mapped[SchoolClass] = relationship()
    questions: Mapped[list["Question"]] = relationship(
        back_populates="exam",
        order_by="Question.position",
        cascade="all, delete-orphan",
    )


class Question(IdMixin, TimestampMixin, Base):
    __tablename__ = "question"
    __table_args__ = (
        UniqueConstraint("exam_id", "position"),
        UniqueConstraint("exam_id", "label"),
        CheckConstraint("max_half_marks > 0", name="max_half_marks_positive"),
    )

    exam_id: Mapped[int] = mapped_column(ForeignKey("exam.id", ondelete="CASCADE"), index=True)
    groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(20))
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    # Integer half-mark units: 2 = one mark (D-018).
    max_half_marks: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)

    exam: Mapped[Exam] = relationship(back_populates="questions")
    points: Mapped[list["MarkSchemePoint"]] = relationship(
        back_populates="question",
        order_by="MarkSchemePoint.position",
        cascade="all, delete-orphan",
    )


class MarkSchemePoint(IdMixin, TimestampMixin, Base):
    __tablename__ = "mark_scheme_point"
    __table_args__ = (
        UniqueConstraint("question_id", "position"),
        CheckConstraint("half_marks > 0", name="half_marks_positive"),
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    # Integer half-mark units: 2 = one mark (D-018).
    half_marks: Mapped[int] = mapped_column(Integer)
    # Other acceptable wordings or answers for this point.
    alternatives: Mapped[list[str]] = mapped_column(JSON, default=list)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer)

    question: Mapped[Question] = relationship(back_populates="points")
