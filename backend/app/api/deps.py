"""Request dependencies: one DB transaction per request, the signed-in user, CSRF, roles."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.auth.sessions import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    csrf_token_matches,
    find_active_session,
)
from app.clock import utcnow
from app.config import Settings
from app.db.models import User, UserSession
from app.errors import AuthenticationError, PermissionDeniedError
from app.services.access import require_admin

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _get_db(request: Request) -> Iterator[Session]:
    """Commit when the handler succeeds, roll back on any error. Runs before the response is
    sent (scope="function"), so a failed commit becomes an error response, not a silent loss."""
    factory: sessionmaker[Session] = request.app.state.sessionmaker
    with factory() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


DbSession = Annotated[Session, Depends(_get_db, scope="function")]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


def get_current_session(request: Request, db: DbSession, settings: AppSettings) -> UserSession:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_session = (
        find_active_session(db, token, settings=settings, now=utcnow()) if token else None
    )
    if user_session is None:
        raise AuthenticationError("Please sign in")
    if request.method not in SAFE_METHODS and not csrf_token_matches(
        user_session, request.headers.get(CSRF_HEADER_NAME)
    ):
        raise PermissionDeniedError("Missing or invalid CSRF token", code="auth.csrf_failed")
    return user_session


CurrentSession = Annotated[UserSession, Depends(get_current_session)]


def get_current_user(user_session: CurrentSession) -> User:
    return user_session.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_admin_user(user: CurrentUser) -> User:
    require_admin(user)
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]
