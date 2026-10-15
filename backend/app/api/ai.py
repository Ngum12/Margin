"""Start AI marking and follow its progress (the full queue screen is Phase 4)."""

from datetime import datetime

from fastapi import APIRouter

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.db.models import ErrorCategory, TranscriptionSource
from app.marks import from_half_marks
from app.schemas.common import ApiModel
from app.services import ai_marking, ai_progress, page_check, system_status

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
    # Empty for a point the teacher marked without an AI proposal (Phase 4).
    proposed_marks: int | float | None
    evidence: str
    confidence: float | None
    error_category: ErrorCategory | None
    model_name: str | None
    model_version: str | None
    prompt_version: str | None
    proposed_at: datetime | None


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
                proposed_marks=(
                    None
                    if d.proposed_half_marks is None
                    else from_half_marks(d.proposed_half_marks)
                ),
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


# --- page check before AI marking (owner, 2026-10-15) -----------------------------------------


class CheckPageOut(ApiModel):
    id: int
    position: int | None
    is_cover: bool
    width: int
    height: int
    rotation: int
    rotation_teacher: int | None


class CheckScriptOut(ApiModel):
    script_id: int
    student_code: str
    student_name: str | None
    status: str
    pages: list[CheckPageOut]


class PageCheckOut(ApiModel):
    exam_id: int
    checked_at: datetime | None
    scripts: list[CheckScriptOut]


def _page_check_out(check: page_check.PageCheck) -> PageCheckOut:
    return PageCheckOut(
        exam_id=check.exam.id,
        checked_at=check.exam.pages_checked_at,
        scripts=[
            CheckScriptOut(
                script_id=item.script.id,
                student_code=item.script.student.code,
                student_name=item.script.student.display_name,
                status=item.script.status.value,
                pages=[
                    CheckPageOut(
                        id=p.id,
                        position=p.position,
                        is_cover=p.is_cover,
                        width=p.width,
                        height=p.height,
                        rotation=p.effective_rotation,
                        rotation_teacher=p.rotation_teacher,
                    )
                    for p in item.pages
                ],
            )
            for item in check.scripts
        ],
    )


@router.get("/exams/{exam_id}/page-check")
def get_page_check(exam_id: int, db: DbSession, user: CurrentUser) -> PageCheckOut:
    return _page_check_out(page_check.page_check(db, user, exam_id))


@router.post("/exams/{exam_id}/page-check")
def confirm_page_check(exam_id: int, db: DbSession, user: CurrentUser) -> PageCheckOut:
    page_check.mark_checked(db, user, exam_id)
    return _page_check_out(page_check.page_check(db, user, exam_id))


# --- live AI progress (owner, 2026-10-15) -----------------------------------------------------


class ScriptProgressOut(ApiModel):
    script_id: int
    student_code: str
    state: str
    step: str | None
    index: int | None
    total: int | None


class LatestReadOut(ApiModel):
    page_id: int
    student_code: str
    text: str
    at: datetime


class AiProgressOut(ApiModel):
    running: bool
    percent: int
    done_units: int
    total_units: int
    eta_seconds: float | None
    ready: int
    manual: int
    current_student: str | None
    current_page_id: int | None
    latest_read: LatestReadOut | None
    scripts: list[ScriptProgressOut]


@router.get("/exams/{exam_id}/ai-progress")
def ai_progress_view(exam_id: int, db: DbSession, user: CurrentUser) -> AiProgressOut:
    progress = ai_progress.exam_progress(db, user, exam_id)
    latest = progress.latest_read
    return AiProgressOut(
        running=progress.running,
        percent=progress.percent,
        done_units=progress.done_units,
        total_units=progress.total_units,
        eta_seconds=None if progress.eta_seconds is None else round(progress.eta_seconds),
        ready=progress.count("ready"),
        manual=progress.count("manual"),
        current_student=progress.current_student,
        current_page_id=progress.current_page_id,
        latest_read=(
            LatestReadOut(
                page_id=latest.page_id,
                student_code=latest.student_code,
                text=latest.text,
                at=latest.at,
            )
            if latest
            else None
        ),
        scripts=[
            ScriptProgressOut(
                script_id=p.script.id,
                student_code=p.script.student.code,
                state=p.state,
                step=p.step,
                index=p.index,
                total=p.total,
            )
            for p in progress.scripts
        ],
    )
