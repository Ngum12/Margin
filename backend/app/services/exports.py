"""Exports (Phase 5) and the export guard (Phase 4).

Every export takes its scripts from ``exportable_scripts`` or checks ``require_confirmed``:
nothing a teacher has not confirmed can ever be exported (brief, non-negotiable). Every export is
audited. Files are written under MARGIN_DATA_DIR and served only through authenticated endpoints.
"""

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import Settings
from app.db.models import (
    Exam,
    Export,
    ExportKind,
    ExportStatus,
    JobType,
    Script,
    ScriptStatus,
    Student,
    User,
)
from app.errors import ConflictError, NotFoundError
from app.exports.dataset import write_dataset
from app.exports.marked_pdf import write_marked_pdf
from app.exports.results_csv import results_csv
from app.services import audit, jobs
from app.services.access import get_visible_exam, get_visible_script, require_admin, visible_exams
from app.services.decisions import exam_questions
from app.services.results import script_results

logger = logging.getLogger(__name__)


def exportable_scripts(db: Session, exam: Exam) -> list[Script]:
    """The exam's confirmed scripts only."""
    return list(
        db.scalars(
            select(Script)
            .where(Script.exam_id == exam.id, Script.status == ScriptStatus.CONFIRMED)
            .order_by(Script.id)
        )
    )


def require_confirmed(script: Script) -> None:
    if script.status != ScriptStatus.CONFIRMED or script.confirmed_at is None:
        raise ConflictError("Only confirmed scripts can be exported", code="export.not_confirmed")


def _slug(text: str) -> str:
    """ASCII file-name part: "Mock exam 1 (Form 5A)" -> "mock-exam-1-form-5a"."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60] or "exam"


def _language(actor: User) -> str:
    return actor.preferred_language.value


def _audit_export(db: Session, actor: User, export: Export, details: dict[str, object]) -> None:
    audit.record(
        db,
        actor=actor,
        entity_type="export",
        entity_id=export.id,
        action="export",
        new_value={"kind": export.kind.value, "exam_id": export.exam_id, **details},
    )


def _record(db: Session, actor: User, kind: ExportKind, exam: Exam | None, filename: str) -> Export:
    export = Export(
        kind=kind,
        exam_id=exam.id if exam else None,
        school_id=actor.school_id,
        requested_by_id=actor.id,
        language=_language(actor),
        filename=filename,
    )
    db.add(export)
    db.flush()
    return export


# --- immediate downloads ----------------------------------------------------------------------


@dataclass(frozen=True)
class Download:
    filename: str
    content: bytes
    media_type: str


def exam_csv(db: Session, actor: User, exam_id: int) -> Download:
    exam = get_visible_exam(db, actor, exam_id)
    scripts = exportable_scripts(db, exam)
    results = script_results(db, exam, scripts)
    content = results_csv(exam_questions(db, exam.id), results, _language(actor))
    filename = f"results-{_slug(exam.title)}.csv"
    export = _record(db, actor, ExportKind.CSV, exam, filename)
    export.status, export.size_bytes, export.finished_at = ExportStatus.DONE, len(content), utcnow()
    _audit_export(db, actor, export, {"scripts": len(results)})
    return Download(filename, content, "text/csv; charset=utf-8")


def student_pdf(db: Session, actor: User, script_id: int, settings: Settings) -> Download:
    script = get_visible_script(db, actor, script_id)
    require_confirmed(script)
    exam = db.get(Exam, script.exam_id)
    if exam is None:  # pragma: no cover
        raise NotFoundError("Exam")
    result = script_results(db, exam, [script], with_pages=True)
    buffer = io.BytesIO()
    write_marked_pdf(buffer, result, exam.title, settings.data_dir, _language(actor))
    content = buffer.getvalue()
    filename = f"{_slug(exam.title)}-{script.student.code}.pdf"
    export = _record(db, actor, ExportKind.STUDENT_PDF, exam, filename)
    export.status, export.size_bytes, export.finished_at = ExportStatus.DONE, len(content), utcnow()
    _audit_export(db, actor, export, {"script_id": script.id})
    return Download(filename, content, "application/pdf")


# --- background exports -----------------------------------------------------------------------


def request_class_pdf(db: Session, actor: User, exam_id: int, settings: Settings) -> Export:
    exam = get_visible_exam(db, actor, exam_id)
    if not exportable_scripts(db, exam):
        raise ConflictError("No confirmed scripts to export", code="export.nothing_confirmed")
    export = _record(
        db, actor, ExportKind.CLASS_PDF, exam, f"{_slug(exam.title)}-marked-scripts.pdf"
    )
    jobs.enqueue(
        db,
        JobType.EXPORT_PDFS,
        {"export_id": export.id},
        f"export:{export.id}",
        max_attempts=settings.job_max_attempts,
    )
    return export


@dataclass(frozen=True)
class ConsentCount:
    exam: Exam
    confirmed: int
    consented: int


def dataset_preview(db: Session, actor: User) -> list[ConsentCount]:
    """Per exam of the school: confirmed scripts, and how many of those have consent."""
    require_admin(actor)
    rows = []
    for exam in db.scalars(visible_exams(actor).order_by(Exam.id)):
        counts = dict(
            db.execute(
                select(Student.training_consent, func.count())
                .join(Script, Script.student_id == Student.id)
                .where(Script.exam_id == exam.id, Script.status == ScriptStatus.CONFIRMED)
                .group_by(Student.training_consent)
            ).all()
        )
        confirmed = sum(counts.values())
        if confirmed:
            rows.append(ConsentCount(exam, confirmed, counts.get(True, 0)))
    return rows


def consented_scripts(db: Session, exam: Exam) -> list[Script]:
    """Confirmed scripts of students with training consent: the only ones in a dataset."""
    return [s for s in exportable_scripts(db, exam) if s.student.training_consent]


def request_dataset(
    db: Session, actor: User, exam_ids: list[int] | None, settings: Settings
) -> Export:
    require_admin(actor)
    exams = _dataset_exams(db, actor, exam_ids)
    if not any(consented_scripts(db, exam) for exam in exams):
        raise ConflictError(
            "No confirmed scripts of consenting students", code="export.nothing_consented"
        )
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    export = _record(db, actor, ExportKind.DATASET, None, f"margin-dataset-{stamp}.zip")
    jobs.enqueue(
        db,
        JobType.EXPORT_DATASET,
        {"export_id": export.id, "exam_ids": [e.id for e in exams]},
        f"export:{export.id}",
        max_attempts=settings.job_max_attempts,
    )
    return export


def _dataset_exams(db: Session, actor: User, exam_ids: list[int] | None) -> list[Exam]:
    query = visible_exams(actor).order_by(Exam.id)
    if exam_ids is not None:
        query = query.where(Exam.id.in_(exam_ids))
    exams = list(db.scalars(query))
    if exam_ids is not None and len(exams) != len(set(exam_ids)):
        raise NotFoundError("Exam")
    return exams


def get_visible_export(db: Session, actor: User, export_id: int) -> Export:
    export = db.get(Export, export_id)
    if export is None or export.school_id != actor.school_id:
        raise NotFoundError("Export")
    if export.kind == ExportKind.DATASET:
        if not actor.is_admin:
            raise NotFoundError("Export")
    elif (
        export.exam_id is None
        or db.scalar(
            visible_exams(actor).where(Exam.id == export.exam_id).with_only_columns(Exam.id)
        )
        is None
    ):
        raise NotFoundError("Export")
    return export


def export_file(export: Export, settings: Settings) -> str:
    """The stored file's path relative to MARGIN_DATA_DIR."""
    if export.status != ExportStatus.DONE or not export.file_path:
        raise ConflictError("The file is not ready", code="export.not_ready")
    return export.file_path


# --- worker side ------------------------------------------------------------------------------


def _target(export: Export, settings: Settings) -> tuple[Path, str]:
    relative = Path("exports") / str(export.id) / (export.filename or f"export-{export.id}")
    path = settings.data_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path, relative.as_posix()


def _finish(db: Session, export: Export, path: Path, relative: str) -> None:
    export.file_path = relative
    export.size_bytes = path.stat().st_size
    export.status = ExportStatus.DONE
    export.finished_at = utcnow()


def build_class_pdf(db: Session, export: Export, settings: Settings) -> None:
    exam = db.get(Exam, export.exam_id) if export.exam_id else None
    user = db.get(User, export.requested_by_id)
    if exam is None or user is None:  # pragma: no cover
        return
    results = script_results(db, exam, exportable_scripts(db, exam), with_pages=True)
    path, relative = _target(export, settings)
    with path.open("wb") as out:
        write_marked_pdf(out, results, exam.title, settings.data_dir, export.language)
    _finish(db, export, path, relative)
    _audit_export(db, user, export, {"scripts": len(results)})


def build_dataset(db: Session, export: Export, exam_ids: list[int], settings: Settings) -> None:
    user = db.get(User, export.requested_by_id)
    if user is None:  # pragma: no cover
        return
    exams = [
        (exam, consented_scripts(db, exam))
        for exam in db.scalars(select(Exam).where(Exam.id.in_(exam_ids)).order_by(Exam.id))
    ]
    path, relative = _target(export, settings)
    counts = write_dataset(db, [(e, s) for e, s in exams if s], settings.data_dir, path)
    _finish(db, export, path, relative)
    _audit_export(
        db,
        user,
        export,
        {"exams": counts.exams, "scripts": counts.scripts, "pages": counts.pages},
    )


def fail(db: Session, export: Export, code: str) -> None:
    export.status = ExportStatus.FAILED
    export.error_code = code
    export.finished_at = utcnow()
