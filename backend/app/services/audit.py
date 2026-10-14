"""Append-only audit log.

``record`` is the only write path. A session-level guard refuses any update or delete of an
``AuditEvent`` through the ORM, so history cannot be rewritten by application code.
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, User


class AuditLogImmutableError(RuntimeError):
    pass


def record(
    db: Session,
    *,
    actor: User | None,
    entity_type: str,
    entity_id: int,
    action: str,
    old_value: Any = None,
    new_value: Any = None,
    reason: str | None = None,
) -> AuditEvent:
    """Add an audit event to the current transaction. It commits with the change it describes."""
    audit_event = AuditEvent(
        actor_id=actor.id if actor else None,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
    )
    db.add(audit_event)
    return audit_event


@event.listens_for(Session, "before_flush")
def _refuse_audit_changes(session: Session, _flush_context: object, _instances: object) -> None:
    for obj in (*session.dirty, *session.deleted):
        if isinstance(obj, AuditEvent) and (
            obj in session.deleted or session.is_modified(obj, include_collections=False)
        ):
            raise AuditLogImmutableError("Audit events are append-only")
