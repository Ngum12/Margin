from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import passwords
from app.auth.sessions import revoke_all_for_user
from app.clock import utcnow
from app.db.models import Language, Role, User
from app.errors import ConflictError, NotFoundError
from app.schemas.accounts import UserCreateIn, UserUpdateIn
from app.services import audit
from app.services.access import require_admin


def _snapshot(user: User) -> dict[str, object]:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role.value,
        "preferred_language": user.preferred_language.value,
        "is_active": user.is_active,
    }


def list_users(db: Session, actor: User) -> list[User]:
    require_admin(actor)
    return list(
        db.scalars(select(User).where(User.school_id == actor.school_id).order_by(User.username))
    )


def get_user(db: Session, actor: User, user_id: int) -> User:
    require_admin(actor)
    user = db.get(User, user_id)
    if user is None or user.school_id != actor.school_id:
        raise NotFoundError("User")
    return user


def create_user(db: Session, actor: User, data: UserCreateIn) -> User:
    require_admin(actor)
    return create_user_unchecked(db, actor, actor.school_id, data)


def create_user_unchecked(
    db: Session, actor: User | None, school_id: int, data: UserCreateIn
) -> User:
    """Create a user without a permission check. Used by the admin API and the setup CLI."""
    if db.scalar(select(User.id).where(User.username == data.username)) is not None:
        raise ConflictError("Username already exists", code="user.username_taken")
    user = User(
        school_id=school_id,
        username=data.username,
        display_name=data.display_name,
        email=data.email,
        password_hash=passwords.hash_password(data.password),
        role=data.role,
        preferred_language=data.preferred_language,
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        action="create",
        new_value=_snapshot(user),
    )
    return user


def _active_admin_count(db: Session, school_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.school_id == school_id, User.role == Role.ADMIN, User.is_active.is_(True))
        )
        or 0
    )


def update_user(db: Session, actor: User, user_id: int, data: UserUpdateIn) -> User:
    user = get_user(db, actor, user_id)
    before = _snapshot(user)
    changes = data.model_dump(exclude_unset=True)

    loses_admin = (
        user.is_admin
        and user.is_active
        and (changes.get("role") == Role.TEACHER or changes.get("is_active") is False)
    )
    if loses_admin and _active_admin_count(db, user.school_id) <= 1:
        raise ConflictError(
            "The school must keep at least one active administrator", code="user.last_admin"
        )
    if user.id == actor.id and changes.get("is_active") is False:
        raise ConflictError(
            "You cannot deactivate your own account", code="user.cannot_deactivate_self"
        )

    for field, value in changes.items():
        # Only email may be cleared; null for any other field means "leave unchanged".
        if value is None and field != "email":
            continue
        setattr(user, field, value)
    if changes.get("is_active") is False:
        revoke_all_for_user(db, user.id, now=utcnow())

    after = _snapshot(user)
    if after != before:
        audit.record(
            db,
            actor=actor,
            entity_type="user",
            entity_id=user.id,
            action="update",
            old_value=before,
            new_value=after,
        )
    return user


def reset_password(db: Session, actor: User, user_id: int, new_password: str) -> None:
    user = get_user(db, actor, user_id)
    user.password_hash = passwords.hash_password(new_password)
    revoke_all_for_user(db, user.id, now=utcnow())
    # Never store passwords or hashes in the audit log.
    audit.record(db, actor=actor, entity_type="user", entity_id=user.id, action="reset_password")


def set_own_language(db: Session, actor: User, language: Language) -> User:
    actor.preferred_language = language
    return actor
