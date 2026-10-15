"""Results (screen 8) and exports (Phase 5). Only confirmed scripts are ever exported."""

from urllib.parse import urlsplit

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.api.deps import AdminUser, AppSettings, CurrentUser, DbSession
from app.api.scans import _data_file
from app.db.models import Export, ExportKind
from app.marks import from_half_marks
from app.schemas.results import (
    ExportOut,
    ModelConfigOut,
    ResultQuestionOut,
    ResultRowOut,
    ResultsOut,
    TrainingExamOut,
    TrainingExportIn,
    TrainingExportOut,
)
from app.services import exports, results

router = APIRouter(tags=["results"])

RECENT_EXPORTS = 10


def _download(download: exports.Download) -> Response:
    return Response(
        download.content,
        media_type=download.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download.filename}"',
            "Cache-Control": "private, no-store",
        },
    )


def _marks(half: int | None) -> int | float | None:
    return None if half is None else from_half_marks(half)


def _average(half: float | None) -> float | None:
    return None if half is None else round(half / 2, 2)


@router.get("/exams/{exam_id}/results")
def exam_results(exam_id: int, db: DbSession, user: CurrentUser) -> ResultsOut:
    found = results.exam_results(db, user, exam_id)
    max_half = sum(q.max_half_marks for q in found.questions)
    rows = []
    for script in found.scripts:
        confirmed = script.confirmed
        total = script.total_half or 0
        rows.append(
            ResultRowOut(
                script_id=script.script.id,
                student_code=script.script.student.code,
                student_name=script.script.student.display_name,
                status=script.script.status,
                confirmed=confirmed,
                marks=[_marks(q.final_half) if confirmed else None for q in script.questions],
                total=from_half_marks(total) if confirmed else None,
                percentage=round(100 * total / max_half, 1) if confirmed and max_half else None,
            )
        )
    timed = [
        found.review_times[s.script.id]
        for s in found.confirmed
        if s.script.id in found.review_times
    ]
    class_pdfs = db.scalars(
        select(Export)
        .where(Export.exam_id == exam_id, Export.kind == ExportKind.CLASS_PDF)
        .order_by(Export.id.desc())
        .limit(RECENT_EXPORTS)
    )
    return ResultsOut(
        exam_id=found.exam.id,
        exam_title=found.exam.title,
        exam_status=found.exam.status,
        questions=[
            ResultQuestionOut(
                id=q.id,
                label=q.label,
                max_marks=from_half_marks(q.max_half_marks),
                average=_average(found.question_average_half(q.id)),
            )
            for q in found.questions
        ],
        rows=rows,
        max_total=from_half_marks(max_half),
        average_total=_average(found.average_total_half),
        confirmed_count=len(found.confirmed),
        script_count=len(found.scripts),
        timed_count=len(timed),
        average_review_seconds=sum(t.wall_seconds for t in timed) / len(timed) if timed else None,
        average_active_seconds=sum(t.active_seconds for t in timed) / len(timed) if timed else None,
        class_pdfs=[ExportOut.model_validate(e) for e in class_pdfs],
    )


@router.get("/exams/{exam_id}/results.csv")
def results_csv(exam_id: int, db: DbSession, user: CurrentUser) -> Response:
    return _download(exports.exam_csv(db, user, exam_id))


@router.get("/scripts/{script_id}/marked.pdf")
def marked_pdf(script_id: int, db: DbSession, user: CurrentUser, settings: AppSettings) -> Response:
    return _download(exports.student_pdf(db, user, script_id, settings))


@router.post("/exams/{exam_id}/exports/class-pdf", status_code=202)
def class_pdf(exam_id: int, db: DbSession, user: CurrentUser, settings: AppSettings) -> ExportOut:
    return ExportOut.model_validate(exports.request_class_pdf(db, user, exam_id, settings))


@router.get("/exports/{export_id}")
def export_status(export_id: int, db: DbSession, user: CurrentUser) -> ExportOut:
    return ExportOut.model_validate(exports.get_visible_export(db, user, export_id))


@router.get("/exports/{export_id}/file")
def export_file(
    export_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> FileResponse:
    export = exports.get_visible_export(db, user, export_id)
    relative = exports.export_file(export, settings)
    media = "application/zip" if export.kind == ExportKind.DATASET else "application/pdf"
    return FileResponse(
        _data_file(settings.data_dir, relative),
        media_type=media,
        filename=export.filename,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/admin/training-export")
def training_preview(db: DbSession, user: AdminUser) -> TrainingExportOut:
    rows = exports.dataset_preview(db, user)
    recent = db.scalars(
        select(Export)
        .where(Export.school_id == user.school_id, Export.kind == ExportKind.DATASET)
        .order_by(Export.id.desc())
        .limit(RECENT_EXPORTS)
    )
    return TrainingExportOut(
        exams=[
            TrainingExamOut(
                exam_id=r.exam.id,
                title=r.exam.title,
                subject_code=r.exam.subject_code,
                confirmed=r.confirmed,
                consented=r.consented,
            )
            for r in rows
        ],
        exports=[ExportOut.model_validate(e) for e in recent],
    )


@router.post("/admin/training-export", status_code=202)
def training_export(
    body: TrainingExportIn, db: DbSession, user: AdminUser, settings: AppSettings
) -> ExportOut:
    return ExportOut.model_validate(exports.request_dataset(db, user, body.exam_ids, settings))


@router.get("/admin/model-config")
def model_config(user: AdminUser, settings: AppSettings) -> ModelConfigOut:
    """Read-only (brief screen 9): models are changed in the configuration, not in the app."""
    mock = settings.ai_backend == "mock"
    return ModelConfigOut(
        ai_backend=settings.ai_backend,
        model_host=urlsplit(settings.model_base_url).netloc,
        reader_model="mock" if mock else settings.reader_model,
        marker_model="mock" if mock else settings.marker_model,
        marker_evidence=settings.marker_evidence,
        model_timeout_seconds=settings.model_timeout_seconds,
        model_output_retries=settings.model_output_retries,
        orientation_check=settings.orientation_check,
    )
