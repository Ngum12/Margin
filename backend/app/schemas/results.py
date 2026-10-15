"""Results and exports (Phase 5). Marks are whole marks (D-018)."""

from datetime import datetime

from pydantic import Field

from app.db.models import ExamStatus, ExportKind, ExportStatus, ScriptStatus
from app.schemas.common import ApiModel
from app.schemas.review import Marks


class ResultQuestionOut(ApiModel):
    id: int
    label: str
    max_marks: Marks
    # Over confirmed scripts; None until one is confirmed.
    average: float | None


class ResultRowOut(ApiModel):
    script_id: int
    student_code: str
    student_name: str | None
    status: ScriptStatus
    confirmed: bool
    # Aligned with ``questions``; None for unconfirmed scripts (nothing is final until confirmed).
    marks: list[Marks | None]
    total: Marks | None
    percentage: float | None
    test_model: bool


class ExportOut(ApiModel):
    id: int
    kind: ExportKind
    status: ExportStatus
    filename: str | None
    size_bytes: int | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


class ResultsOut(ApiModel):
    exam_id: int
    exam_title: str
    exam_status: ExamStatus
    questions: list[ResultQuestionOut]
    rows: list[ResultRowOut]
    max_total: Marks
    average_total: float | None
    confirmed_count: int
    script_count: int
    # Class averages over confirmed scripts with recorded review time (owner change 2).
    timed_count: int
    average_review_seconds: float | None
    average_active_seconds: float | None
    class_pdfs: list[ExportOut]
    test_model_count: int


class TrainingExamOut(ApiModel):
    exam_id: int
    title: str
    subject_code: str
    confirmed: int
    consented: int


class TrainingExportOut(ApiModel):
    exams: list[TrainingExamOut]
    exports: list[ExportOut]


class TrainingExportIn(ApiModel):
    # None: every exam of the school.
    exam_ids: list[int] | None = Field(default=None, max_length=1000)


class ModelConfigOut(ApiModel):
    ai_backend: str
    model_host: str
    reader_model: str
    marker_model: str
    marker_evidence: str
    model_timeout_seconds: int
    model_output_retries: int
    orientation_check: str
