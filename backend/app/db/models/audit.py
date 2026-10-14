from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.db.base import Base, IdMixin, UTCDateTime


class AuditEvent(IdMixin, Base):
    """Append-only record of changes. Updates and deletes are refused (see app.services.audit)."""

    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_event_entity", "entity_type", "entity_id"),)

    # Null for system actions (e.g. the worker).
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(50))
    # JSON snapshots; None (SQL NULL) when there is no old or new value.
    old_value: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
