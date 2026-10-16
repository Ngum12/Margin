"""Private sign-in slips: idempotent PIN issuance and the existing local print queue."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import PrintJob, User
from app.errors import NotFoundError
from app.exports import fonts
from app.schemas.portal import CredentialIn
from app.services import audit, student_auth
from app.services.scan_inbox import hardware


def issue_slips(db: Session, actor: User, data: CredentialIn, settings: Settings) -> PrintJob:
    key = f"credentials:{actor.school_id}:{data.key}"
    old = db.scalar(select(PrintJob).where(PrintJob.request_key == key))
    if old:
        if old.requested_by_id != actor.id and not actor.is_admin:
            raise NotFoundError("Print")
        return old
    # Validate every student before changing any credential; the request is one transaction.
    from app.services.access import get_visible_student

    for student_id in set(data.student_ids):
        get_visible_student(db, actor, student_id)
    fonts.register()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    french = actor.preferred_language.value == "fr"
    for student_id in dict.fromkeys(data.student_ids):
        student, pin = student_auth.issue(db, actor, student_id, reset=data.reset)
        canvas.setFont(fonts.REGULAR, 18)
        canvas.drawString(
            55, 770, "Margin — Connexion élève" if french else "Margin — Student sign-in"
        )
        canvas.setFont(fonts.REGULAR, 13)
        for y, text in [
            (720, student.display_name or student.code),
            (680, f"Code: {student.code}"),
            (640, f"PIN: {pin}"),
            (
                590,
                "Changez ce PIN à la première connexion."
                if french
                else "Change this PIN when you first sign in.",
            ),
            (
                555,
                "Gardez ce papier privé. Déconnectez-vous après utilisation."
                if french
                else "Keep this slip private. Sign out after use.",
            ),
            (520, "Adresse / Address: _________________________________"),
        ]:
            canvas.drawString(55, y, text)
        canvas.showPage()
    canvas.save()
    config = hardware(db, actor.school_id)
    job = PrintJob(
        school_id=actor.school_id,
        requested_by_id=actor.id,
        request_key=key,
        kind="student_credentials",
        language=actor.preferred_language.value,
        printer_uri=config.printer_uri or "",
        duplex=False,
        status="queued" if config.printer_uri else "failed",
        error_code=None if config.printer_uri else "hardware.printer_missing",
    )
    db.add(job)
    db.flush()
    relative = f"student-credentials/{job.id}.pdf"
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(buffer.getvalue())
    job.file_path = relative
    audit.record(
        db,
        actor=actor,
        entity_type="print_job",
        entity_id=job.id,
        action="print_credentials",
        new_value={"student_ids": data.student_ids},
    )
    return job
