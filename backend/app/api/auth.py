from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response

from app.api.deps import AppSettings, CurrentSession, CurrentUser, DbSession
from app.auth.sessions import SESSION_COOKIE_NAME, create_session, revoke_session
from app.clock import utcnow
from app.errors import PermissionDeniedError
from app.schemas.accounts import LanguageIn, LoginIn, MeOut, SchoolOut, UserOut
from app.services import auth as auth_service
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _check_same_origin(request: Request) -> None:
    """Login has no session yet, so no CSRF token: require the browser's Origin (or Referer)
    to match the host it is talking to. Requests without either (non-browser) are allowed."""
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return
    if urlsplit(source).netloc != request.headers.get("host", ""):
        raise PermissionDeniedError("Cross-origin sign-in refused", code="auth.csrf_failed")


def _me(session_csrf: str, user: CurrentUser) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(user),
        school=SchoolOut.model_validate(user.school),
        csrf_token=session_csrf,
    )


@router.post("/login")
def login(
    data: LoginIn, request: Request, response: Response, db: DbSession, settings: AppSettings
) -> MeOut:
    _check_same_origin(request)
    now = utcnow()
    user = auth_service.authenticate(
        db,
        data.username,
        data.password,
        settings=settings,
        now=now,
        client_ip=request.client.host if request.client else None,
    )
    new = create_session(
        db, user, settings=settings, now=now, user_agent=request.headers.get("user-agent")
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        new.token,
        max_age=settings.session_absolute_hours * 3600,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return _me(new.session.csrf_token, user)


@router.post("/logout", status_code=204)
def logout(user_session: CurrentSession, response: Response, settings: AppSettings) -> None:
    revoke_session(user_session, now=utcnow())
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


@router.get("/me")
def me(user_session: CurrentSession) -> MeOut:
    return _me(user_session.csrf_token, user_session.user)


@router.put("/me/language")
def set_language(data: LanguageIn, user_session: CurrentSession, db: DbSession) -> MeOut:
    user = user_service.set_own_language(db, user_session.user, data.preferred_language)
    return _me(user_session.csrf_token, user)
