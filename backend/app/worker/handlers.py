"""Job handlers. Each is idempotent: running it again after a crash skips work already stored.

Errors:
- ModelUnavailableError (server down, timeout, model not pulled) propagates: the job is retried
  with backoff.
- ModelOutputInvalidError after the allowed retries: the script is flagged for manual marking
  with a reason and the job completes. Nothing is invented and nothing partial is stored for
  the failed item.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.factory import build_marker, build_reader
from app.ai.types import (
    ModelCallTimeoutError,
    ModelInfo,
    ModelOutputInvalidError,
    PageImage,
    PageText,
    Reader,
)
from app.ai.types import Transcription as AiTranscription
from app.ai.validation import ORIENTATION_TURN
from app.clock import utcnow
from app.config import Settings
from app.db.models import (
    Exam,
    Export,
    ExportStatus,
    JobType,
    MarkDecision,
    ModelCall,
    ModelRole,
    ModelVersion,
    Page,
    PageState,
    School,
    Script,
    ScriptStatus,
    Transcription,
    TranscriptionSource,
)
from app.marks import to_half_marks
from app.services import audit, exports, jobs, transcripts, uploads
from app.services.ai_marking import exam_spec, mark_key, update_exam_progress
from app.services.identification import identify_spare
from app.subjects.registry import SubjectConfig, get_registry

logger = logging.getLogger(__name__)


class MissingTranscriptionError(Exception):
    """Marking was asked for before every page had a transcription (retried)."""


def _register_model(db: Session, model: ModelInfo, role: ModelRole) -> None:
    exists = db.scalar(
        select(ModelVersion.id).where(
            ModelVersion.name == model.name,
            ModelVersion.version == model.version,
            ModelVersion.role == role,
        )
    )
    if exists is None:
        db.add(ModelVersion(name=model.name, version=model.version, role=role, source=model.source))


def _curriculum(db: Session, exam: Exam) -> str:
    school = db.get(School, exam.school_class.school_id)
    return school.curriculum if school else ""


def _answer_pages(db: Session, script: Script) -> list[Page]:
    return list(
        db.scalars(
            select(Page)
            .where(
                Page.script_id == script.id,
                Page.state == PageState.ASSIGNED,
                Page.is_cover.is_(False),
            )
            .order_by(Page.position)
        )
    )


def _flag_manual(db: Session, script: Script, reason: str) -> None:
    script.manual_reason = reason
    audit.record(
        db,
        actor=None,
        entity_type="script",
        entity_id=script.id,
        action="flag_manual",
        new_value={"reason": reason},
    )
    logger.warning("Script %s flagged for manual marking: %s", script.id, reason)


def process_upload(
    factory: sessionmaker[Session], settings: Settings, payload: dict[str, int]
) -> None:
    uploads.process_upload(factory, settings, payload["upload_id"])


def transcribe_script(
    factory: sessionmaker[Session], settings: Settings, payload: dict[str, int]
) -> None:
    reader = build_reader(settings)
    with factory() as db:
        script = db.get(Script, payload["script_id"])
        if script is None or script.manual_reason or script.status != ScriptStatus.WAITING:
            return
        exam = db.get(Exam, script.exam_id)
        if exam is None:  # pragma: no cover
            return
        subject = get_registry().get(_curriculum(db, exam), exam.subject_code)
        if subject is None:  # pragma: no cover
            return
        _register_model(db, reader.model, ModelRole.READER)
        script.ai_started_at = script.ai_started_at or utcnow()
        db.commit()
        pages = _answer_pages(db, script)
        if not pages:
            _flag_manual(db, script, "ai.no_answer_pages")
            db.commit()
            update_exam_progress(db, script.exam_id)
            db.commit()
            return

        for number, page in enumerate(pages, start=1):
            done = db.scalar(
                select(Transcription.id).where(
                    Transcription.page_id == page.id,
                    Transcription.source == TranscriptionSource.MODEL,
                    Transcription.model_name == reader.model.name,
                    Transcription.model_version == reader.model.version,
                    Transcription.prompt_version == reader.prompt_version,
                )
            )
            if done is not None:
                continue  # resumed after a restart
            _set_step(db, script, "reading", number, len(pages), page.id)
            started = time.monotonic()
            try:
                result = _read_page(db, reader, settings, page, subject)
            except ModelOutputInvalidError as exc:
                _set_step(db, script, None)
                # Literal reasons: tests check every one is translated.
                if isinstance(exc, ModelCallTimeoutError):
                    _flag_manual(db, script, "ai.reader_timeout")
                else:
                    _flag_manual(db, script, "ai.reader_invalid_output")
                db.commit()
                update_exam_progress(db, script.exam_id)
                db.commit()
                return
            db.add(
                Transcription(
                    script_id=script.id,
                    page_id=page.id,
                    text=result.pages[0].text,
                    source=TranscriptionSource.MODEL,
                    model_name=result.model.name,
                    model_version=result.model.version,
                    prompt_version=result.prompt_version,
                    created_at=result.created_at,
                    rotation=page.effective_rotation,
                )
            )
            _record_call(db, ModelRole.READER, reader.model.name, time.monotonic() - started)
            try:
                db.commit()  # each page is kept as soon as it is done
            except IntegrityError:  # pragma: no cover - another worker stored it first
                db.rollback()

        _set_step(db, script, None)
        script.status = ScriptStatus.TRANSCRIBED
        jobs.enqueue(
            db,
            JobType.MARK_SCRIPT,
            {"script_id": script.id},
            mark_key(script.id),
            max_attempts=settings.job_max_attempts,
            requeue=True,
        )
        db.commit()


def _read_page(
    db: Session, reader: Reader, settings: Settings, page: Page, subject: SubjectConfig
) -> AiTranscription:
    """Read one answer page; if the Reader judges it not upright with enough confidence, turn it
    and read it once more, keeping the second read (orientation layer c, owner change 1)."""
    from app.services.answer_sheets import grading_image

    image = settings.data_dir / page.image_path
    sidecar = image.with_suffix(".txt")

    def read() -> AiTranscription:
        masked, rotation = grading_image(db, page, settings)
        return reader.transcribe(
            [
                PageImage(
                    page.id,
                    masked,
                    sidecar if sidecar.is_file() else None,
                    rotation=rotation,
                )
            ],
            subject,
        )

    result = read()
    if settings.orientation_check != "reader" or page.rotation_teacher is not None:
        return result
    judged = result.pages[0]
    turn = ORIENTATION_TURN.get(judged.orientation or "", 0)
    confidence = judged.orientation_confidence or 0.0
    if turn == 0 or confidence < settings.orientation_min_confidence:
        return result
    old = page.effective_rotation
    page.rotation_auto = (page.rotation_auto + turn) % 360
    page.auto_rotation_confidence = confidence
    page.auto_rotation_model = result.model.name
    page.auto_rotation_prompt_version = result.prompt_version
    audit.record(
        db,
        actor=None,
        entity_type="page",
        entity_id=page.id,
        action="auto_rotate",
        old_value={"rotation": old},
        new_value={
            "rotation": page.effective_rotation,
            "orientation": judged.orientation,
            "confidence": confidence,
        },
    )
    logger.info(
        "Page %s judged %s (%.2f); read again turned", page.id, judged.orientation, confidence
    )
    # The second read's own judgement is kept in the logs only: never a further rotation.
    return read()


def _set_step(
    db: Session,
    script: Script,
    step: str | None,
    index: int | None = None,
    total: int | None = None,
    page_id: int | None = None,
) -> None:
    """Record what the worker is doing now, for the live progress view. Committed at once and
    kept apart from the results (no AI output is pending when this is called)."""
    script.ai_step = step
    script.ai_step_index = index
    script.ai_step_total = total
    script.ai_step_page_id = page_id
    script.ai_step_started_at = utcnow() if step else None
    db.commit()


def _record_call(db: Session, role: ModelRole, model: str, seconds: float) -> None:
    db.add(ModelCall(role=role, model_name=model, seconds=round(seconds, 2)))


class _QuestionTimer:
    """Marks each question's start in the progress view and times the previous question."""

    def __init__(self, db: Session, script: Script, model: str) -> None:
        self._db, self._script, self._model = db, script, model
        self._started: float | None = None

    def _close_previous(self) -> None:
        if self._started is not None:
            _record_call(self._db, ModelRole.MARKER, self._model, time.monotonic() - self._started)

    def next_question(self, number: int, total: int) -> None:
        self._close_previous()
        self._started = time.monotonic()
        _set_step(self._db, self._script, "marking", number, total)

    def finish(self) -> None:
        self._close_previous()
        self._started = None
        _set_step(self._db, self._script, None)


def _line_refs(texts: list[PageText], numbers: tuple[int, ...]) -> list[list[int]] | None:
    """Map line numbers of the combined answer (pages joined by a blank line, as
    Transcription.full_text) to [page id, line index within that page]."""
    if not numbers:
        return None
    where: list[tuple[int, int] | None] = []
    for index, page in enumerate(texts):
        if index:
            where.append(None)  # the blank line between pages
        where.extend((page.page_id, n) for n in range(len(page.text.split("\n"))))
    refs: list[list[int]] = []
    for n in numbers:
        ref = where[n - 1] if 0 < n <= len(where) else None
        if ref is not None:
            refs.append([ref[0], ref[1]])
    return refs or None


def _latest_texts(db: Session, pages: list[Page]) -> list[PageText]:
    """Per page, the current transcription (see services.transcripts.current)."""
    texts = []
    for page in pages:
        found = transcripts.current(transcripts.page_versions(db, page.id))
        if found is None:
            raise MissingTranscriptionError(f"page {page.id}")
        texts.append(PageText(page.id, found.text))
    return texts


def transcribe_page(
    factory: sessionmaker[Session], settings: Settings, payload: dict[str, int]
) -> None:
    """A fresh read of one page that a teacher asked for after correcting its orientation. The
    teacher's orientation is final, so the Reader's own judgement is not acted on here."""
    reader = build_reader(settings)
    with factory() as db:
        page = db.get(Page, payload["page_id"])
        if page is None or page.script_id is None:
            return
        script = db.get(Script, page.script_id)
        exam = db.get(Exam, script.exam_id) if script else None
        if script is None or exam is None or script.status == ScriptStatus.CONFIRMED:
            return
        subject = get_registry().get(_curriculum(db, exam), exam.subject_code)
        if subject is None:  # pragma: no cover
            return
        _register_model(db, reader.model, ModelRole.READER)
        rotation = page.effective_rotation
        done = db.scalar(
            select(Transcription.id).where(
                Transcription.page_id == page.id,
                Transcription.source == TranscriptionSource.MODEL,
                Transcription.model_name == reader.model.name,
                Transcription.model_version == reader.model.version,
                Transcription.prompt_version == reader.prompt_version,
                Transcription.rotation == rotation,
            )
        )
        if done is None:
            from app.services.answer_sheets import grading_image

            image, image_rotation = grading_image(db, page, settings)
            try:
                result = reader.transcribe(
                    [PageImage(page.id, image, rotation=image_rotation)], subject
                )
            except ModelOutputInvalidError:
                logger.warning("Fresh read of page %s failed validation", page.id)
                audit.record(
                    db,
                    actor=None,
                    entity_type="page",
                    entity_id=page.id,
                    action="retranscribe_failed",
                )
                db.commit()
                return
            db.add(
                Transcription(
                    script_id=script.id,
                    page_id=page.id,
                    text=result.pages[0].text,
                    source=TranscriptionSource.MODEL,
                    model_name=result.model.name,
                    model_version=result.model.version,
                    prompt_version=result.prompt_version,
                    created_at=result.created_at,
                    rotation=rotation,
                )
            )
        page.rotated_after_transcription = False
        db.commit()


def mark_script(
    factory: sessionmaker[Session], settings: Settings, payload: dict[str, int]
) -> None:
    marker = build_marker(settings)
    with factory() as db:
        script = db.get(Script, payload["script_id"])
        if script is None or script.manual_reason or script.status != ScriptStatus.TRANSCRIBED:
            return
        exam = db.get(Exam, script.exam_id)
        if exam is None:  # pragma: no cover
            return
        _register_model(db, marker.model, ModelRole.MARKER)
        db.commit()

        already = db.scalar(
            select(MarkDecision.id)
            .where(
                MarkDecision.script_id == script.id,
                MarkDecision.model_name == marker.model.name,
                MarkDecision.model_version == marker.model.version,
                MarkDecision.prompt_version == marker.prompt_version,
                MarkDecision.ai_run == script.ai_run,
            )
            .limit(1)
        )
        if already is None:
            texts = _latest_texts(db, _answer_pages(db, script))
            transcription = AiTranscription(texts, marker.model, marker.prompt_version, utcnow())
            timer = _QuestionTimer(db, script, marker.model.name)
            marker.on_question = timer.next_question
            try:
                proposal = marker.mark(transcription, exam_spec(exam, _curriculum(db, exam)))
            finally:
                marker.on_question = None
                timer.finish()
            for question in proposal.questions:
                for point in question.points:
                    db.add(
                        MarkDecision(
                            script_id=script.id,
                            mark_scheme_point_id=point.point_id,
                            proposed_half_marks=to_half_marks(point.awarded_marks),
                            evidence=point.evidence,
                            confidence=point.confidence,
                            error_category=point.error_category,
                            model_name=proposal.model.name,
                            model_version=proposal.model.version,
                            prompt_version=proposal.prompt_version,
                            proposed_at=proposal.created_at,
                            ai_run=script.ai_run,
                            evidence_refs=_line_refs(texts, point.evidence_lines),
                        )
                    )
            if proposal.failed_question_ids:
                # Proposals for the other questions are kept; the teacher marks the rest.
                _flag_manual(db, script, "ai.marker_invalid_output")
        if script.manual_reason is None:
            script.status = ScriptStatus.AI_MARKED
        db.commit()  # all decisions for the script in one transaction
        update_exam_progress(db, script.exam_id)
        db.commit()


def _run_export(
    factory: sessionmaker[Session],
    payload: dict[str, Any],
    build: Callable[[Session, Export], None],
) -> None:
    """Build one export file. A failure marks the export failed (shown to the teacher) and
    completes the job: retrying would not help a broken file and must not loop."""
    with factory() as db:
        export = db.get(Export, payload["export_id"])
        if export is None or export.status != ExportStatus.PENDING:
            return  # already built (resumed after a restart) or removed
        try:
            build(db, export)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Export %s failed", payload["export_id"])
            export = db.get(Export, payload["export_id"])
            if export is not None:
                exports.fail(db, export, "export.failed")
                db.commit()


def export_pdfs(
    factory: sessionmaker[Session], settings: Settings, payload: dict[str, Any]
) -> None:
    _run_export(factory, payload, lambda db, e: exports.build_class_pdf(db, e, settings))


def export_dataset(
    factory: sessionmaker[Session], settings: Settings, payload: dict[str, Any]
) -> None:
    exam_ids = [int(i) for i in payload.get("exam_ids", [])]
    _run_export(factory, payload, lambda db, e: exports.build_dataset(db, e, exam_ids, settings))


HANDLERS = {
    JobType.IDENTIFY_SPARE: identify_spare,
    JobType.PROCESS_UPLOAD: process_upload,
    JobType.TRANSCRIBE_SCRIPT: transcribe_script,
    JobType.MARK_SCRIPT: mark_script,
    JobType.TRANSCRIBE_PAGE: transcribe_page,
    JobType.EXPORT_PDFS: export_pdfs,
    JobType.EXPORT_DATASET: export_dataset,
}
