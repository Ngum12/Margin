"""Confirmed-only printing, with an explicit uncertain state across hardware failures."""

import io
from datetime import timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Frame, KeepInFrame, Paragraph, Spacer
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.clock import utcnow
from app.config import Settings
from app.db.models import Exam, PrintJob, Script, ScriptStatus, User
from app.errors import ConflictError, NotFoundError
from app.exports import fonts
from app.exports.marked_pdf import write_marked_pdf
from app.services import audit, ipp
from app.services.access import get_visible_exam, visible_exams
from app.services.decisions import current_decisions
from app.services.exports import _add_red_pen, require_confirmed
from app.services.results import ScriptResult, script_results
from app.services.scan_inbox import hardware


def visible_jobs(db: Session, actor: User) -> list[PrintJob]:
    query = select(PrintJob).where(PrintJob.school_id == actor.school_id)
    if not actor.is_admin:
        query = query.where(
            or_(
                PrintJob.exam_id.in_(visible_exams(actor).with_only_columns(Exam.id)),
                PrintJob.requested_by_id == actor.id,
            )
        )
    return list(db.scalars(query.order_by(PrintJob.id.desc()).limit(100)))


def request_print(
    db: Session,
    actor: User,
    exam_id: int | None,
    script_ids: list[int] | None,
    key: str,
    kind: str,
    unprinted: bool = False,
) -> PrintJob:
    config = hardware(db, actor.school_id)
    if not config.printer_uri:
        raise ConflictError("Configure a printer first", code="hardware.no_printer")
    existing = db.scalar(select(PrintJob).where(PrintJob.request_key == f"{actor.id}:{key}"))
    if existing:
        return existing
    scripts: list[Script] = []
    if exam_id is not None:
        if kind == "test":
            raise ConflictError(
                "Test pages cannot represent student scripts", code="hardware.print_failed"
            )
        exam = get_visible_exam(db, actor, exam_id)
        scripts = list(
            db.scalars(
                select(Script).where(
                    Script.exam_id == exam.id, Script.status == ScriptStatus.CONFIRMED
                )
            )
        )
        if script_ids is not None:
            scripts = [s for s in scripts if s.id in script_ids]
            if len(scripts) != len(set(script_ids)):
                raise ConflictError(
                    "Only confirmed scripts can be printed", code="export.not_confirmed"
                )
        if unprinted:
            printed = {
                i
                for job in db.scalars(
                    select(PrintJob).where(
                        PrintJob.exam_id == exam.id, PrintJob.status == "printed"
                    )
                )
                for i in job.script_ids
                if job.confirmation_versions.get(str(i))
                == next(
                    (s.confirmed_at.isoformat() for s in scripts if s.id == i and s.confirmed_at),
                    None,
                )
            }
            scripts = [s for s in scripts if s.id not in printed]
        if not scripts:
            raise ConflictError("No confirmed scripts to print", code="export.nothing_confirmed")
        # Stable insertion order is the initial register order; roster imports preserve it.
        scripts.sort(key=lambda s: s.student_id)
    elif not actor.is_admin or kind != "test":
        raise NotFoundError("Exam")
    row = PrintJob(
        school_id=actor.school_id,
        requested_by_id=actor.id,
        exam_id=exam_id,
        request_key=f"{actor.id}:{key}",
        script_ids=[s.id for s in scripts],
        confirmation_versions={
            str(s.id): s.confirmed_at.isoformat() for s in scripts if s.confirmed_at
        },
        kind=kind,
        language=actor.preferred_language.value,
        printer_uri=config.printer_uri,
        duplex=config.duplex if kind != "feedback" else False,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity_type="print_job",
        entity_id=row.id,
        action="request",
        new_value={"scripts": row.script_ids, "kind": kind},
    )
    return row


def feedback_pdf(db: Session, results: list[ScriptResult], title: str, language: str) -> bytes:
    fonts.register()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    french = language == "fr"
    style = ParagraphStyle("feedback", fontName=fonts.REGULAR, fontSize=10, leading=15)
    decisions = current_decisions(db, [r.script.id for r in results])
    for result in results:
        script = result.script
        teacher = db.get(User, script.confirmed_by_id) if script.confirmed_by_id else None
        paragraphs = [
            Paragraph(escape(title), style),
            Paragraph(escape(script.student.display_name or script.student.code), style),
            Spacer(1, 14),
        ]
        if result.test_model:
            paragraphs.append(Paragraph("MODÈLE DE TEST / TEST MODEL", style))
        for question in result.questions:
            text = (
                f"{question.question.label}: {(question.final_half or 0) / 2:g} / "
                f"{question.question.max_half_marks / 2:g}"
            )
            paragraphs.append(Paragraph(escape(text), style))
            if question.comment:
                paragraphs.append(Paragraph(escape(question.comment), style))
            for point in question.points:
                decision = decisions.get((script.id, point.point_id))
                if decision and decision.evidence_refs and point.final_half != point.max_half:
                    locations = ", ".join(
                        f"page {p}, {'ligne' if french else 'line'} {line + 1}"
                        for page_id, line in decision.evidence_refs
                        for p in [
                            next((pg.position for pg in script.pages if pg.id == page_id), None)
                        ]
                        if p is not None
                    )
                    category = (
                        point.final_category.value if point.final_category else "review"
                    ).replace("_", " ")
                    if french:
                        category = {
                            "conceptual error": "erreur de compréhension",
                            "language expression": "expression",
                            "transcription uncertain": "lecture incertaine",
                            "omitted": "réponse manquante",
                            "correct": "correct",
                            "review": "à vérifier",
                        }.get(category, category)
                    # References are evidence positions; never invent a location from prose.
                    paragraphs.append(
                        Paragraph(
                            escape(f"{question.question.label}, {locations}: {category}"), style
                        )
                    )
            paragraphs.append(Spacer(1, 6))
        paragraphs.append(
            Paragraph(f"Total: {(result.total_half or 0) / 2:g} / {result.max_half / 2:g}", style)
        )
        content = KeepInFrame(A4[0] - 80, A4[1] - 125, paragraphs, mode="shrink")
        Frame(
            40,
            85,
            A4[0] - 80,
            A4[1] - 125,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        ).addFromList([content], canvas)
        footer = (
            "Corrigé avec l'aide de Margin IA, vérifié et confirmé par "
            if french
            else "Marked with Margin AI assistance, reviewed and confirmed by "
        ) + (teacher.display_name if teacher else "—")
        Paragraph(
            escape(footer), ParagraphStyle("footer", fontName=fonts.REGULAR, fontSize=8, leading=11)
        ).wrapOn(canvas, A4[0] - 80, 40)
        note = Paragraph(
            escape(footer), ParagraphStyle("footer", fontName=fonts.REGULAR, fontSize=8, leading=11)
        )
        note.wrapOn(canvas, A4[0] - 80, 40)
        note.drawOn(canvas, 40, 35)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def build_document(db: Session, job: PrintJob, settings: Settings) -> bytes:
    if job.kind == "test":
        buffer = io.BytesIO()
        canvas = Canvas(buffer, pagesize=A4)
        canvas.drawString(60, 750, "Margin - Printer test / Test imprimante - A4")
        canvas.showPage()
        canvas.save()
        return buffer.getvalue()
    if job.kind == "student_credentials" and job.file_path:
        actor = db.get(User, job.requested_by_id)
        if actor is None or not actor.is_active or actor.school_id != job.school_id:
            raise NotFoundError("Requester")
        return (settings.data_dir / job.file_path).read_bytes()
    exam = db.get(Exam, job.exam_id)
    if exam is None:
        raise NotFoundError("Exam")
    scripts = []
    actor = db.get(User, job.requested_by_id)
    if actor is None or not actor.is_active:
        raise ConflictError("Requester no longer active", code="hardware.print_changed")
    get_visible_exam(db, actor, exam.id)
    if job.kind == "answer_sheets" and job.file_path:
        return (settings.data_dir / job.file_path).read_bytes()
    for script_id in job.script_ids:
        script = db.get(Script, script_id)
        if script is None or script.exam_id != exam.id:
            raise NotFoundError("Script")
        require_confirmed(script)
        if (
            not script.confirmed_at
            or script.confirmed_at.isoformat() != job.confirmation_versions.get(str(script.id))
        ):
            raise ConflictError(
                "Marks changed; request a fresh print", code="hardware.print_changed"
            )
        scripts.append(script)
    results = script_results(db, exam, scripts, with_pages=True)
    results.sort(key=lambda r: job.script_ids.index(r.script.id))
    if job.kind == "feedback":
        return feedback_pdf(db, results, exam.title, job.language)
    _add_red_pen(db, results, settings, job.language)
    buffer = io.BytesIO()
    write_marked_pdf(
        buffer, results, exam.title, settings.data_dir, job.language, duplex=job.duplex
    )
    return buffer.getvalue()


def retry(db: Session, actor: User, job_id: int, acknowledge_uncertain: bool) -> PrintJob:
    job = next((j for j in visible_jobs(db, actor) if j.id == job_id), None)
    if job is None:
        raise NotFoundError("Print job")
    if job.status not in ("failed", "unknown") or (
        job.status == "unknown" and not acknowledge_uncertain
    ):
        raise ConflictError("Check the printer before retrying", code="hardware.print_uncertain")
    if not job.printer_uri:
        job.printer_uri = hardware(db, actor.school_id).printer_uri or ""
    job.status, job.error_code, job.printer_job_id = "queued", None, None
    audit.record(
        db,
        actor=actor,
        entity_type="print_job",
        entity_id=job.id,
        action="retry",
        new_value={"checked_printer": acknowledge_uncertain},
    )
    return job


def tick(factory: sessionmaker[Session], settings: Settings) -> None:
    with factory() as db:
        # Submission was committed before the network operation. Never resend it on restart.
        for job in db.scalars(
            select(PrintJob).where(
                PrintJob.status == "submitting",
                PrintJob.updated_at < utcnow() - timedelta(seconds=120),
            )
        ):
            job.status, job.error_code = "unknown", "hardware.print_uncertain"
        for job in db.scalars(select(PrintJob).where(PrintJob.status == "sent")):
            try:
                state = ipp.job_state(job.printer_uri, job.printer_job_id or 0)
                if state == 9:
                    job.status, job.error_code = "printed", None
                    audit.record(
                        db, actor=None, entity_type="print_job", entity_id=job.id, action="printed"
                    )
                elif state in (7, 8):
                    # A cancelled/aborted job may already have printed some pages.
                    job.status, job.error_code = "unknown", "hardware.print_uncertain"
            except ipp.PrinterError as exc:
                job.error_code = str(exc)
        db.commit()
        pending = db.scalar(
            select(PrintJob).where(PrintJob.status == "queued").order_by(PrintJob.id).limit(1)
        )
        if pending is None:
            return
        job = pending
        # Claim before producing hardware side effects.
        claimed = db.scalar(
            update(PrintJob)
            .where(PrintJob.id == job.id, PrintJob.status == "queued")
            .values(status="submitting")
            .returning(PrintJob.id)
        )
        db.commit()
        if claimed is None:
            return
        try:
            document = build_document(db, job, settings)
            ipp.capabilities(job.printer_uri)
        except Exception as exc:
            job.status, job.error_code = (
                "failed",
                getattr(
                    exc,
                    "code",
                    str(exc) if isinstance(exc, ipp.PrinterError) else "hardware.print_failed",
                ),
            )
            db.commit()
            return
        relative = Path("prints") / f"{job.id}.pdf"
        path = settings.data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document)
        job.file_path, job.status = relative.as_posix(), "submitting"
        if job.kind == "feedback":
            job.duplex = False  # Also protect jobs queued by an earlier application version.
        db.commit()
        try:
            job.printer_job_id = ipp.submit(
                job.printer_uri, document, f"Margin-{job.id}", job.duplex
            )
            job.status, job.error_code = "sent", None
        except ipp.PrinterError:
            job.status, job.error_code = "unknown", "hardware.print_uncertain"
        audit.record(db, actor=None, entity_type="print_job", entity_id=job.id, action=job.status)
        db.commit()
