from datetime import datetime

from pydantic import Field

from app.db.models import PageState, ScriptStatus, UnassignedReason, UploadStatus
from app.schemas.common import ApiModel


class CoverSheetRowOut(ApiModel):
    student_id: int
    code: str
    display_name: str | None
    has_sheet: bool


class UploadOut(ApiModel):
    id: int
    original_filename: str
    sha256: str
    size_bytes: int
    page_count: int | None
    status: UploadStatus
    error_code: str | None
    created_at: datetime
    processed_at: datetime | None


class PageOut(ApiModel):
    id: int
    upload_id: int
    source_page_index: int
    is_cover: bool
    state: PageState
    position: int | None
    unassigned_reason: UnassignedReason | None
    related_page_id: int | None
    # For "other_exam": the title of that exam, only if the viewer may see it.
    detected_exam_title: str | None = None
    width: int
    height: int


class StudentRef(ApiModel):
    id: int
    code: str
    display_name: str | None


class ScriptOut(ApiModel):
    id: int
    student: StudentRef
    status: ScriptStatus
    pages: list[PageOut]


class ScriptsOut(ApiModel):
    scripts: list[ScriptOut]
    # Students of the class with no script yet.
    missing: list[StudentRef]


class PageIdsIn(ApiModel):
    page_ids: list[int] = Field(min_length=1, max_length=1000)


class AssignPagesIn(PageIdsIn):
    student_id: int
