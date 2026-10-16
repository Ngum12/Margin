"""PIN credentials and short independent student sessions; no staff privilege inheritance."""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.passwords import burn_verification_time, hash_password, verify_password
from app.clock import utcnow
from app.db.models import School, Student, User
from app.db.models.portal import StudentAccount, StudentLoginAttempt, StudentSession
from app.errors import AuthenticationError, ConflictError, TooManyAttemptsError
from app.schemas.portal import PortalSettings
from app.services import audit
from app.services.access import get_visible_student

COOKIE = "margin_student"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def policy(db: Session, school_id: int) -> PortalSettings:
    school = db.get(School, school_id)
    return PortalSettings.model_validate(school.portal_settings if school else {})


def issue(db: Session, actor: User, student_id: int, *, reset: bool) -> tuple[Student, str]:
    student = get_visible_student(db, actor, student_id)
    account = db.scalar(select(StudentAccount).where(StudentAccount.student_id == student.id))
    if account and not reset:
        raise ConflictError("Credentials already issued")
    pin = "".join(secrets.choice("0123456789") for _ in range(8))
    if account is None:
        account = StudentAccount(student_id=student.id, pin_hash=hash_password(pin))
        db.add(account)
        db.flush()
    else:
        account.pin_hash = hash_password(pin)
        account.must_change_pin = True
        account.is_active = True
        account.pin_changed_at = utcnow()
        for session in db.scalars(
            select(StudentSession).where(StudentSession.account_id == account.id)
        ):
            session.revoked_at = utcnow()
    audit.record(
        db,
        actor=actor,
        entity_type="student",
        entity_id=student.id,
        action="reset_pin" if reset else "issue_pin",
    )
    return student, pin


def login(db: Session, school_id: int, code: str, pin: str, ip: str) -> tuple[StudentSession, str]:
    now = utcnow()
    code = code.strip().upper()
    hashed = digest(code)
    recent = select(StudentLoginAttempt).where(
        StudentLoginAttempt.attempted_at > now - timedelta(minutes=15),
        StudentLoginAttempt.succeeded.is_(False),
    )
    account_fails = (
        db.scalar(
            select(func.count()).select_from(
                recent.where(
                    StudentLoginAttempt.school_id == school_id,
                    StudentLoginAttempt.code_hash == hashed,
                ).subquery()
            )
        )
        or 0
    )
    ip_fails = (
        db.scalar(
            select(func.count()).select_from(
                recent.where(StudentLoginAttempt.client_ip == ip).subquery()
            )
        )
        or 0
    )
    if account_fails >= 5 or ip_fails >= 30:
        raise TooManyAttemptsError("Try again in fifteen minutes")
    account = db.scalar(
        select(StudentAccount)
        .join(Student)
        .where(Student.school_id == school_id, Student.code == code)
    )
    ok = False
    if account:
        ok = (
            verify_password(account.pin_hash, pin)
            and account.is_active
            and policy(db, school_id).enabled
        )
    else:
        burn_verification_time(pin)
    if db.get(School, school_id):
        db.add(
            StudentLoginAttempt(school_id=school_id, code_hash=hashed, client_ip=ip, succeeded=ok)
        )
    if not ok or account is None:
        db.commit()
        raise AuthenticationError("Code or PIN incorrect", code="auth.invalid_credentials")
    token = secrets.token_urlsafe(32)
    session = StudentSession(
        account_id=account.id,
        token_hash=digest(token),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=now + timedelta(hours=1),
    )
    db.add(session)
    db.flush()
    return session, token


def active(db: Session, token: str | None) -> StudentSession:
    session = (
        db.scalar(select(StudentSession).where(StudentSession.token_hash == digest(token)))
        if token
        else None
    )
    now = utcnow()
    if (
        session is None
        or session.revoked_at
        or session.expires_at <= now
        or not session.account.is_active
    ):
        raise AuthenticationError("Sign in")
    rules = policy(db, session.account.student.school_id)
    if not rules.enabled or session.last_seen_at + timedelta(minutes=rules.idle_minutes) <= now:
        raise AuthenticationError("Sign in")
    session.last_seen_at = now
    return session


def change_pin(db: Session, session: StudentSession, old: str, new: str) -> None:
    account = session.account
    if old == new or not verify_password(account.pin_hash, old):
        raise ConflictError("Check current PIN and choose a different PIN")
    account.pin_hash = hash_password(new)
    account.must_change_pin = False
    account.pin_changed_at = utcnow()
    for other in db.scalars(
        select(StudentSession).where(
            StudentSession.account_id == account.id, StudentSession.id != session.id
        )
    ):
        other.revoked_at = utcnow()
    audit.record(
        db, actor=None, entity_type="student", entity_id=account.student_id, action="change_pin"
    )
