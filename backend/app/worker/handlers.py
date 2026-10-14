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
from app.ai.types import ModelInfo, ModelOutputInvalidError, PageImage, PageText
from app.ai.types import Transcription as AiTranscription
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
from app.services import audit, jobs, uploads
from app.services.ai_marking import exam_spec, mark_key, update_exam_progress
from app.subjects.registry import get_registry

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
            image = settings.data_dir / page.image_path
            sidecar = image.with_suffix(".txt")
            try:
                result = reader.transcribe(
                    [PageImage(page.id, image, sidecar if sidecar.is_file() else None)], subject
                )
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


def _latest_texts(db: Session, pages: list[Page]) -> list[PageText]:
    """Per page, the newest teacher transcription if any, otherwise the newest model one."""
    texts = []
    for page in pages:
        rows = db.scalars(
            select(Transcription)
            .where(Transcription.page_id == page.id)
            .order_by(Transcription.created_at.desc(), Transcription.id.desc())
        ).all()
        if not rows:
            raise MissingTranscriptionError(f"page {page.id}")
        teacher = [r for r in rows if r.source == TranscriptionSource.TEACHER]
        texts.append(PageText(page.id, (teacher or rows)[0].text))
    return texts


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
}
