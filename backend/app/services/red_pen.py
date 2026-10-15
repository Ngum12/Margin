"""Red pen layouts for a script (owner, 2026-10-15): the data the marked PDF and the review screen
draw on each answer page. No model is involved.

For each point the teacher's decision is used; where there is none yet, the AI's proposal is
shown as "pending" (the screen draws it lighter; the PDF only ever prints confirmed scripts).
Evidence positions come from the transcription the AI marked; a page whose text the teacher
changed since then uses the current text and places only what it can find.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    MarkDecision,
    Page,
    PageState,
    Question,
    QuestionComment,
    Script,
    Transcription,
)
from app.marks import from_half_marks
from app.redpen.align import align
from app.redpen.ink import Band, detect_lines
from app.redpen.layout import (
    CROSS,
    PARTIAL,
    TICK,
    PageLayout,
    PointMark,
    QuestionMarks,
    layout_page,
    question_starts,
)
from app.services import transcripts
from app.services.decisions import current_decisions, exam_questions
from app.services.results import QuestionResult


@dataclass(frozen=True)
class ScriptRedPen:
    pages: dict[int, PageLayout]  # by page id (answer pages only)
    total: str


def upright_image(path: Path, rotation: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    return image.rotate(-(rotation % 360), expand=True) if rotation % 360 else image


def _point_mark(decision: MarkDecision | None, max_half: int, point_id: int) -> PointMark | None:
    if decision is None:
        return None
    half = decision.final_half_marks
    pending = half is None
    if half is None:
        half = decision.proposed_half_marks
    if half is None:
        return None
    if half >= max_half:
        sign, earned = TICK, ""
    elif half == 0:
        sign, earned = CROSS, ""
    else:
        sign, earned = PARTIAL, f"{from_half_marks(half)}/{from_half_marks(max_half)}"
    return PointMark(point_id, sign, earned, (), pending)


def _text_for_page(db: Session, page: Page, marked_at: object) -> list[str]:
    """The page's text as the AI marked it (its line numbers are what the evidence refers to)."""
    versions = transcripts.page_versions(db, page.id)
    if marked_at is not None:
        before = [v for v in versions if v.created_at <= marked_at]  # type: ignore[operator]
        if before:
            return before[-1].text.split("\n")
    found: Transcription | None = transcripts.current(versions)
    return found.text.split("\n") if found else []


def script_red_pen(
    db: Session,
    script: Script,
    data_dir: Path,
    *,
    question_results: list[QuestionResult] | None = None,
) -> ScriptRedPen:
    questions = exam_questions(db, script.exam_id)
    decisions = current_decisions(db, [script.id])
    if question_results is not None:
        comments = {q.question.id: q.comment for q in question_results}
    else:
        comments = {
            c.question_id: c.text
            for c in db.scalars(
                select(QuestionComment).where(QuestionComment.script_id == script.id)
            )
        }
    proposed = [d.proposed_at for d in decisions.values() if d.proposed_at is not None]
    marked_at = min(proposed) if proposed else None

    per_question: list[tuple[Question, list[tuple[PointMark, list[list[int]]]], str]] = []
    total_half = max_half = 0
    for question in questions:
        marks = []
        half_sum = 0
        for point in question.points:
            decision = decisions.get((script.id, point.id))
            mark = _point_mark(decision, point.half_marks, point.id)
            if mark is None:
                continue
            refs = (decision.evidence_refs or []) if decision else []
            marks.append((mark, refs))
            if decision is not None:
                half = decision.final_half_marks
                half_sum += half if half is not None else (decision.proposed_half_marks or 0)
        capped = min(half_sum, question.max_half_marks)
        total_half += capped
        max_half += question.max_half_marks
        score = f"{from_half_marks(capped)}/{from_half_marks(question.max_half_marks)}"
        per_question.append((question, marks, score))
    total = f"{from_half_marks(total_half)}/{from_half_marks(max_half)}"

    pages = [p for p in script.pages if p.state == PageState.ASSIGNED and not p.is_cover]
    labels = [q.label for q, _, _ in per_question]
    texts = {page.id: _text_for_page(db, page, marked_at) for page in pages}
    starts = {page.id: question_starts(texts[page.id], labels) for page in pages}
    layouts: dict[int, PageLayout] = {}
    for index, page in enumerate(pages):
        on_page: list[QuestionMarks] = []
        for question, marks, score in per_question:
            starts_here = question.label in starts[page.id]
            point_marks = tuple(
                PointMark(
                    mark.point_id,
                    mark.sign,
                    mark.earned,
                    tuple(r[1] for r in refs if r[0] == page.id),
                    mark.pending,
                )
                for mark, refs in marks
                # Evidence on this page, or crosses and refless marks at the question's start.
                if any(r[0] == page.id for r in refs)
                or (starts_here and not refs)
                or (starts_here and mark.sign == CROSS)
            )
            if starts_here or point_marks:
                on_page.append(
                    QuestionMarks(
                        question.id,
                        question.label,
                        score if starts_here else "",
                        point_marks,
                        comments.get(question.id, "") if starts_here else "",
                    )
                )
        bands: list[Band] = detect_lines(
            upright_image(data_dir / page.image_path, page.effective_rotation)
        )
        alignment = align(texts[page.id], bands)
        layouts[page.id] = layout_page(
            texts[page.id], bands, alignment, on_page, total=total if index == 0 else None
        )
    return ScriptRedPen(layouts, total)
