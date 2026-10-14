import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent
from app.services import audit
from app.services.audit import AuditLogImmutableError
from tests.conftest import World


def _event(db: Session, world: World) -> AuditEvent:
    event = audit.record(
        db, actor=world.admin, entity_type="exam", entity_id=1, action="create", new_value={"a": 1}
    )
    db.commit()
    return event


def test_record_stores_actor_entity_and_values(db: Session, world: World) -> None:
    event = _event(db, world)

    stored = db.get(AuditEvent, event.id)
    assert stored is not None
    assert (stored.actor_id, stored.entity_type, stored.action) == (
        world.admin.id,
        "exam",
        "create",
    )
    assert stored.new_value == {"a": 1}
    assert stored.created_at.tzinfo is not None


def test_audit_events_cannot_be_updated(db: Session, world: World) -> None:
    event = _event(db, world)
    event.new_value = {"a": 2}

    with pytest.raises(AuditLogImmutableError):
        db.commit()


def test_audit_events_cannot_be_deleted(db: Session, world: World) -> None:
    event = _event(db, world)
    db.delete(event)

    with pytest.raises(AuditLogImmutableError):
        db.commit()


def test_audit_module_exposes_no_update_or_delete() -> None:
    public = {name for name in vars(audit) if not name.startswith("_")}

    assert not {n for n in public if "update" in n or "delete" in n or "remove" in n}


def test_system_actions_have_no_actor(db: Session, world: World) -> None:
    audit.record(db, actor=None, entity_type="job", entity_id=1, action="run")
    db.commit()

    assert db.scalars(select(AuditEvent.actor_id)).one() is None
