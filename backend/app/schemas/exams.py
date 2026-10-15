from datetime import date, datetime

from app.db.models import ExamStatus
from app.schemas.common import ApiModel, IssueOut, RequiredShortText
from app.schemas.mark_scheme import MarkSchemeIn


class ExamCreateIn(ApiModel):
    class_id: int
    subject_code: RequiredShortText
    title: RequiredShortText
    exam_date: date | None = None


class ExamUpdateIn(ApiModel):
    subject_code: RequiredShortText | None = None
    title: RequiredShortText | None = None
    exam_date: date | None = None


class ExamStatusIn(ApiModel):
    status: ExamStatus


class ScriptCounts(ApiModel):
    waiting: int = 0
    ai_marked: int = 0
    confirmed: int = 0


class ExamSummaryOut(ApiModel):
    id: int
    class_id: int
    class_name: str
    subject_code: str
    title: str
    exam_date: date | None
    status: ExamStatus
    question_count: int
    total_marks: int | float
    scripts: ScriptCounts
    updated_at: datetime
    show_scheme_to_students: bool


class PointOut(ApiModel):
    id: int
    description: str
    marks: int | float
    alternatives: list[str]


class QuestionOut(ApiModel):
    id: int
    label: str
    prompt_text: str
    max_marks: int | float
    points: list[PointOut]


class ValidationReportOut(ApiModel):
    blocking: list[IssueOut]
    readiness: list[IssueOut]
    notices: list[IssueOut]
    is_ready: bool


class ExamDetailOut(ExamSummaryOut):
    questions: list[QuestionOut]
    validation: ValidationReportOut


class ImportPreviewOut(ApiModel):
    scheme: MarkSchemeIn | None
    issues: list[IssueOut]
    validation: ValidationReportOut | None


class SubjectOut(ApiModel):
    code: str
    name_en: str
    name_fr: str
