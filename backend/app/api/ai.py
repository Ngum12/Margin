"""Start AI marking and follow its progress (the full queue screen is Phase 4)."""

from datetime import datetime

from fastapi import APIRouter

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.db.models import ErrorCategory, TranscriptionSource
from app.marks import from_half_marks
from app.schemas.common import ApiModel
from app.services import ai_marking, system_status

router = APIRouter(tags=["ai"])


class StartOut(ApiModel):
    scripts_queued: int


class FlaggedOut(ApiModel):
    script_id: int
    student_code: str
    reason: str


class SystemStatusOut(ApiModel):
    worker_online: bool
    ai_backend: str
    model_server_reachable: bool
    reader_model: str
    reader_model_installed: bool
    marker_model: str
    marker_model_installed: bool


class AiStatusOut(ApiModel):
    scripts: dict[str, int]
    flagged: list[FlaggedOut]
    jobs_queued: int
    jobs_running: int
    jobs_failed: int
    system: SystemStatusOut


class TranscriptionOut(ApiModel):
    id: int
    page_id: int
    text: str
    source: TranscriptionSource
    model_name: str | None
    model_version: str | None
    prompt_version: str | None
    created_at: datetime


class DecisionOut(ApiModel):
    id: int
    mark_scheme_point_id: int
    proposed_marks: int | float
    evidence: str
    confidence: float
    error_category: ErrorCategory
    model_name: str
    model_version: str
    prompt_version: str
    proposed_at: datetime


class AiResultsOut(ApiModel):
    script_id: int
    status: str
    manual_reason: str | None
    transcriptions: list[TranscriptionOut]
    decisions: list[DecisionOut]


def _system(db: DbSession, settings: AppSettings) -> SystemStatusOut:
    model = system_status.model_server_status(settings)
    return SystemStatusOut(
        worker_online=system_status.worker_online(db),
        ai_backend=model.backend,
        model_server_reachable=model.reachable,
        reader_model=settings.reader_model if model.backend == "ollama" else "mock",
        reader_model_installed=model.reader_model_installed,
        marker_model=settings.marker_model if model.backend == "ollama" else "mock",
        marker_model_installed=model.marker_model_installed,
    )


@router.get("/system/status")
def system(db: DbSession, user: CurrentUser, settings: AppSettings) -> SystemStatusOut:
    return _system(db, settings)


@router.post("/exams/{exam_id}/ai-marking", status_code=202)
def start(exam_id: int, db: DbSession, user: CurrentUser, settings: AppSettings) -> StartOut:
    return StartOut(scripts_queued=ai_marking.start_ai_marking(db, user, exam_id, settings))


@router.get("/exams/{exam_id}/ai-status")
def status(exam_id: int, db: DbSession, user: CurrentUser, settings: AppSettings) -> AiStatusOut:
    result = ai_marking.ai_status(db, user, exam_id)
    return AiStatusOut(
        scripts=result.by_status,
        flagged=[FlaggedOut(script_id=i, student_code=c, reason=r) for i, c, r in result.flagged],
        jobs_queued=result.jobs_queued,
        jobs_running=result.jobs_running,
        jobs_failed=result.jobs_failed,
        system=_system(db, settings),
    )


@router.get("/scripts/{script_id}/ai-results")
def results(script_id: int, db: DbSession, user: CurrentUser) -> AiResultsOut:
    found = ai_marking.script_ai_results(db, user, script_id)
    return AiResultsOut(
        script_id=found.script.id,
        status=found.script.status.value,
        manual_reason=found.script.manual_reason,
        transcriptions=[TranscriptionOut.model_validate(t) for t in found.transcriptions],
        decisions=[
            DecisionOut(
                id=d.id,
                mark_scheme_point_id=d.mark_scheme_point_id,
                proposed_marks=from_half_marks(d.proposed_half_marks),
                evidence=d.evidence,
                confidence=d.confidence,
                error_category=d.error_category,
                model_name=d.model_name,
                model_version=d.model_version,
                prompt_version=d.prompt_version,
                proposed_at=d.proposed_at,
            )
            for d in found.decisions
        ],
    )
