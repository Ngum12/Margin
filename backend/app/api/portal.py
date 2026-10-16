"""Separate student authentication and explicit staff release/remark actions."""

import hmac
import io
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import select

from app.api.auth import _check_same_origin
from app.api.deps import SAFE_METHODS, AdminUser, AppSettings, CurrentUser, DbSession
from app.auth.sessions import SESSION_COOKIE_NAME, find_active_session, revoke_session
from app.clock import utcnow
from app.db.models import Page, PageState, PrintJob, School, Student
from app.db.models.portal import StudentSession
from app.errors import NotFoundError, PermissionDeniedError
from app.schemas.portal import (
    ChangePin,
    CredentialIn,
    PortalSettings,
    ReleaseIn,
    RemarkIn,
    RemarkReply,
    StudentLogin,
)
from app.services import audit, credentials, portal, student_auth
from app.services.access import get_visible_exam
from app.services.red_pen import script_red_pen

router = APIRouter(tags=["student portal"])


def session_dep(request: Request, response: Response, db: DbSession) -> StudentSession:
    response.headers["Cache-Control"] = "no-store"
    session = student_auth.active(db, request.cookies.get(student_auth.COOKIE))
    if request.method not in SAFE_METHODS and not hmac.compare_digest(
        session.csrf_token, request.headers.get("x-csrf-token", "")
    ):
        raise PermissionDeniedError("Invalid CSRF token", code="auth.csrf_failed")
    return session


StudentSessionDep = Annotated[StudentSession, Depends(session_dep)]


def student_dep(session: StudentSessionDep) -> Student:
    if session.account.must_change_pin:
        raise PermissionDeniedError("Change your initial PIN first", code="portal.change_pin")
    return session.account.student


CurrentStudent = Annotated[Student, Depends(student_dep)]


def me(session: StudentSession, db: DbSession) -> dict[str, Any]:
    return {
        "idle_minutes": student_auth.policy(db, session.account.student.school_id).idle_minutes,
        "code": session.account.student.code,
        "name": session.account.student.display_name,
        "must_change_pin": session.account.must_change_pin,
        "csrf_token": session.csrf_token,
    }


@router.get("/student/schools")
def schools(db: DbSession, response: Response) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    return [
        {"id": s.id, "name": s.name}
        for s in db.scalars(select(School))
        if student_auth.policy(db, s.id).enabled
    ]


@router.post("/student/login")
def login(
    data: StudentLogin, request: Request, response: Response, db: DbSession, settings: AppSettings
) -> dict[str, Any]:
    _check_same_origin(request)
    session, token = student_auth.login(
        db,
        data.school_id,
        data.code,
        data.pin,
        request.client.host if request.client else "unknown",
    )
    staff_token = request.cookies.get(SESSION_COOKIE_NAME)
    if staff_token:
        staff = find_active_session(db, staff_token, settings=settings, now=utcnow())
        if staff:
            revoke_session(staff, now=utcnow())
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.set_cookie(
        student_auth.COOKIE,
        token,
        max_age=3600,
        path="/api/student",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return me(session, db)


@router.get("/student/me")
def whoami(session: StudentSessionDep, db: DbSession) -> dict[str, Any]:
    return me(session, db)


@router.post("/student/logout", status_code=204)
def logout(session: StudentSessionDep, response: Response, settings: AppSettings) -> None:
    session.revoked_at = utcnow()
    response.delete_cookie(
        student_auth.COOKIE,
        path="/api/student",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.put("/student/pin")
def change_pin(data: ChangePin, session: StudentSessionDep, db: DbSession) -> dict[str, Any]:
    student_auth.change_pin(db, session, data.old_pin, data.pin)
    return me(session, db)


@router.get("/student/exams")
def exams(student: CurrentStudent, db: DbSession) -> list[dict[str, Any]]:
    return portal.my_exams(db, student)


@router.get("/student/scripts/{script_id}")
def script(script_id: int, student: CurrentStudent, db: DbSession) -> dict[str, Any]:
    return portal.detail(db, student, script_id)


@router.get("/student/pages/{page_id}/image")
def image(page_id: int, student: CurrentStudent, db: DbSession, settings: AppSettings) -> Response:
    page = db.get(Page, page_id)
    if not page or page.script_id is None or page.state != PageState.ASSIGNED:
        raise NotFoundError("Page")
    portal.own_script(db, student, page.script_id)
    if page.effective_rotation:
        with Image.open(settings.data_dir / page.image_path) as original:
            upright = original.rotate(-page.effective_rotation, expand=True)
            buffer = io.BytesIO()
            upright.save(buffer, format="PNG")
        return Response(
            buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"}
        )
    return FileResponse(settings.data_dir / page.image_path, headers={"Cache-Control": "no-store"})


@router.get("/student/scripts/{script_id}/marks")
def overlay(
    script_id: int, student: CurrentStudent, db: DbSession, settings: AppSettings
) -> dict[str, Any]:
    script, _ = portal.own_script(db, student, script_id)
    layout = script_red_pen(db, script, settings.data_dir)
    # Notes and scheme have a separate filtered endpoint; overlays contain marks only.
    return {
        "pages": [
            {
                "page_id": page_id,
                "marks": [
                    mark.__dict__
                    for mark in page.marks
                    if mark.kind in {"tick", "cross", "partial", "score", "total"}
                ],
            }
            for page_id, page in layout.pages.items()
        ]
    }


@router.post("/student/scripts/{script_id}/remarks")
def request_remark(
    script_id: int, data: RemarkIn, student: CurrentStudent, db: DbSession
) -> dict[str, Any]:
    return portal.remark_out(portal.request_remark(db, student, script_id, data))


@router.post("/student/remarks/{remark_id}/escalate")
def escalate(remark_id: int, student: CurrentStudent, db: DbSession) -> dict[str, Any]:
    return portal.remark_out(portal.escalate(db, student, remark_id))


@router.post("/student/remarks/{remark_id}/seen", status_code=204)
def seen(remark_id: int, student: CurrentStudent, db: DbSession) -> None:
    portal.student_remark(db, student, remark_id).student_seen_at = utcnow()


@router.get("/portal/settings")
def settings_get(actor: CurrentUser, db: DbSession) -> PortalSettings:
    return student_auth.policy(db, actor.school_id)


@router.put("/portal/settings")
def settings_put(data: PortalSettings, actor: AdminUser, db: DbSession) -> PortalSettings:
    old = actor.school.portal_settings
    actor.school.portal_settings = data.model_dump()
    audit.record(
        db,
        actor=actor,
        entity_type="school",
        entity_id=actor.school_id,
        action="portal_settings",
        old_value=old,
        new_value=data.model_dump(),
    )
    return data


@router.get("/exams/{exam_id}/release")
def release_get(exam_id: int, actor: CurrentUser, db: DbSession) -> dict[str, Any]:
    exam = get_visible_exam(db, actor, exam_id)
    return {
        "released": exam.released_at is not None,
        "visibility": exam.student_visibility,
        "released_at": exam.released_at,
    }


@router.put("/exams/{exam_id}/release")
def release_put(exam_id: int, data: ReleaseIn, actor: CurrentUser, db: DbSession) -> dict[str, Any]:
    portal.release(db, actor, exam_id, data)
    return release_get(exam_id, actor, db)


@router.get("/remarks")
def remarks(actor: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    return portal.staff_requests(db, actor)


@router.post("/remarks/{remark_id}/open")
def open_remark(remark_id: int, actor: CurrentUser, db: DbSession) -> dict[str, Any]:
    r = portal.staff_remark(db, actor, remark_id)
    if r.status == "sent":
        r.status = "looking"
    return portal.remark_out(r)


@router.post("/remarks/{remark_id}/reply")
def reply(remark_id: int, data: RemarkReply, actor: CurrentUser, db: DbSession) -> dict[str, Any]:
    return portal.remark_out(portal.reply(db, actor, remark_id, data))


@router.post("/portal/credentials")
def issue(
    data: CredentialIn, actor: CurrentUser, db: DbSession, settings: AppSettings
) -> dict[str, Any]:
    job = credentials.issue_slips(db, actor, data, settings)
    return {"id": job.id, "status": job.status}


@router.get("/portal/credentials/{job_id}.pdf")
def slip(job_id: int, actor: CurrentUser, db: DbSession, settings: AppSettings) -> FileResponse:
    job = db.get(PrintJob, job_id)
    if (
        not job
        or job.school_id != actor.school_id
        or job.kind != "student_credentials"
        or not job.file_path
        or (not actor.is_admin and job.requested_by_id != actor.id)
    ):
        raise NotFoundError("Slip")
    return FileResponse(
        settings.data_dir / job.file_path,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )
