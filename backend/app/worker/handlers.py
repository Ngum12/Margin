"""Job handlers. Each is idempotent: running it again after a crash skips work already stored.

Errors:
- ModelUnavailableError (server down, timeout, model not pulled) propagates: the job is retried
  with backoff.
- ModelOutputInvalidError after the allowed retries: the script is flagged for manual marking
  with a reason and the job completes. Nothing is invented and nothing partial is stored for
  the failed item.
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.factory import build_marker, build_reader
from app.ai.types import ModelInfo, ModelOutputInvalidError, PageImage, PageText, Reader
from app.ai.types import Transcription as AiTranscription
from app.ai.validation import ORIENTATION_TURN
from app.clock import utcnow
from app.config import Settings
from app.db.models import (
    Exam,
    JobType,
    MarkDecision,
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
from app.services import audit, jobs, transcripts, uploads
from app.services.ai_marking import exam_spec, mark_key, update_exam_progress
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

        for page in pages:
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
            try:
                result = _read_page(db, reader, settings, page, subject)
            except ModelOutputInvalidError:
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
            try:
                db.commit()  # each page is kept as soon as it is done
            except IntegrityError:  # pragma: no cover - another worker stored it first
                db.rollback()

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
    image = settings.data_dir / page.image_path
    sidecar = image.with_suffix(".txt")

    def read() -> AiTranscription:
        return reader.transcribe(
            [
                PageImage(
                    page.id,
                    image,
                    sidecar if sidecar.is_file() else None,
                    rotation=page.effective_rotation,
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
            image = settings.data_dir / page.image_path
            try:
                result = reader.transcribe([PageImage(page.id, image, rotation=rotation)], subject)
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
            )
            .limit(1)
        )
        if already is None:
            texts = _latest_texts(db, _answer_pages(db, script))
            transcription = AiTranscription(texts, marker.model, marker.prompt_version, utcnow())
            proposal = marker.mark(transcription, exam_spec(exam, _curriculum(db, exam)))
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


HANDLERS = {
    JobType.PROCESS_UPLOAD: process_upload,
    JobType.TRANSCRIBE_SCRIPT: transcribe_script,
    JobType.MARK_SCRIPT: mark_script,
    JobType.TRANSCRIBE_PAGE: transcribe_page,
}
