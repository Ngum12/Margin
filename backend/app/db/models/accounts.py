from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.db.types import str_enum


class Role(StrEnum):
    ADMIN = "admin"
    TEACHER = "teacher"


class Language(StrEnum):
    EN = "en"
    FR = "fr"


class School(IdMixin, TimestampMixin, Base):
    __tablename__ = "school"

    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(100))
    # Curriculum code, e.g. "cm_gce_ol". Matches subject config files.
    curriculum: Mapped[str] = mapped_column(String(50))


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "user"

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), index=True)
    # Stored lower-cased; sign-in is case-insensitive.
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    preferred_language: Mapped[Language] = mapped_column(
        str_enum(Language, "preferred_language"), default=Language.EN
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    school: Mapped[School] = relationship()

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN


class UserSession(IdMixin, Base):
    __tablename__ = "user_session"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    # SHA-256 of the cookie token. The raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    user_agent: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship()


class LoginAttempt(IdMixin, Base):
    __tablename__ = "login_attempt"
    __table_args__ = (Index("ix_login_attempt_username_time", "username", "attempted_at"),)

    username: Mapped[str] = mapped_column(String(64))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    attempted_at: Mapped[datetime] = mapped_column(UTCDateTime())
    client_ip: Mapped[str | None] = mapped_column(String(64))
