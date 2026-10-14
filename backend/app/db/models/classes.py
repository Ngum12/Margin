from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.db.models.accounts import User


class SchoolClass(IdMixin, TimestampMixin, Base):
    """A teaching group. Named ``school_class`` because ``class`` is reserved in Python."""

    __tablename__ = "school_class"
    __table_args__ = (UniqueConstraint("school_id", "name", "academic_year"),)

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    academic_year: Mapped[str] = mapped_column(String(20))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    teacher: Mapped[User] = relationship()


class Student(IdMixin, TimestampMixin, Base):
    __tablename__ = "student"
    __table_args__ = (UniqueConstraint("school_id", "code"),)

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("school_class.id"), index=True)
    # Pseudonymous code printed on cover sheets and the only identifier models ever see.
    code: Mapped[str] = mapped_column(String(16))
    # Optional real name. Local database only: never sent to a model, never logged.
    display_name: Mapped[str | None] = mapped_column(String(200))
    training_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    consent_recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))

    school_class: Mapped[SchoolClass] = relationship()
