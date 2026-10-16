"""Class results (Phase 5, screen 8) and the data behind every export.

Marks follow the review screen exactly: a question's mark is the sum of its points' final marks,
capped at the question maximum; a total is the sum of capped question marks. Only confirmed
scripts are ever exported (``services.exports``); the screen also lists the others, without
marks.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.validation import evidence_is_quoted
from app.db.models import (
    ErrorCategory,
    Exam,
    Page,
    PageState,
    Question,
    QuestionComment,
    Script,
    ScriptStatus,
    User,
)
from app.services import transcripts
from app.services.access import get_visible_exam
from app.services.decisions import current_decisions, exam_questions
from app.services.provenance import marker_models, test_model_scripts
from app.services.scoring import score_question

if TYPE_CHECKING:
    from app.services.red_pen import ScriptRedPen
from app.services.review import ReviewTime, review_times


@dataclass(frozen=True)
class PointResult:
    point_id: int
    description: str
    max_half: int
    final_half: int | None
    final_category: ErrorCategory | None
    evidence: str


@dataclass(frozen=True)
class QuestionResult:
    question: Question
    points: list[PointResult]
    comment: str

    @property
    def final_half(self) -> int | None:
        return score_question(self.question, {p.point_id: p.final_half for p in self.points})


@dataclass(frozen=True)
class ResultPage:
    page: Page
    text: str


@dataclass
class ScriptResult:
    script: Script
    questions: list[QuestionResult]
    pages: list[ResultPage] = field(default_factory=list)
    # Output from a test model (Mock): labelled in every export (owner, 2026-10-15).
    test_model: bool = False
    models: list[str] = field(default_factory=list)
    # Red pen layout and the confirming teacher's name for the marked PDF (filled in by the
    # exports service).
    red_pen: "ScriptRedPen | None" = None
    confirmed_by_name: str | None = None

    @property
    def confirmed(self) -> bool:
        return self.script.status == ScriptStatus.CONFIRMED

    @property
    def total_half(self) -> int | None:
        marks = [q.final_half for q in self.questions if q.final_half is not None]
        return sum(marks) if marks else None

    @property
    def max_half(self) -> int:
        return sum(q.question.max_half_marks for q in self.questions)

    @property
    def confirmed_at(self) -> datetime | None:
        return self.script.confirmed_at

    def pages_for_question(self, question_id: int) -> list[int]:
        """Answer pages (by page id) whose current text contains evidence for the question."""
        question = next(q for q in self.questions if q.question.id == question_id)
        found = []
        for result_page in self.pages:
            if result_page.page.is_cover or not result_page.text:
                continue
            if any(
                p.evidence and evidence_is_quoted(p.evidence, result_page.text)
                for p in question.points
            ):
                found.append(result_page.page.id)
        return found


def script_results(
    db: Session, exam: Exam, scripts: list[Script], *, with_pages: bool = False
) -> list[ScriptResult]:
    questions = exam_questions(db, exam.id)
    decisions = current_decisions(db, [s.id for s in scripts])
    comments = {
        (c.script_id, c.question_id): c.text
        for c in db.scalars(
            select(QuestionComment).where(QuestionComment.script_id.in_([s.id for s in scripts]))
        )
    }
    tested = test_model_scripts(db, [s.id for s in scripts])
    models = marker_models(db, [s.id for s in scripts])
    results = []
    for script in scripts:
        question_results = []
        for question in questions:
            points = []
            for point in question.points:
                d = decisions.get((script.id, point.id))
                points.append(
                    PointResult(
                        point_id=point.id,
                        description=point.description,
                        max_half=point.half_marks,
                        final_half=d.final_half_marks if d else None,
                        final_category=d.final_category if d else None,
                        evidence=d.evidence if d else "",
                    )
                )
            question_results.append(
                QuestionResult(question, points, comments.get((script.id, question.id), ""))
            )
        result = ScriptResult(
            script,
            question_results,
            test_model=script.id in tested,
            models=models.get(script.id, []),
        )
        if with_pages:
            for page in script.pages:
                if page.state != PageState.ASSIGNED:
                    continue
                found = transcripts.current(transcripts.page_versions(db, page.id))
                result.pages.append(ResultPage(page, found.text if found else ""))
        results.append(result)
    results.sort(key=lambda r: r.script.student.code)
    return results


@dataclass(frozen=True)
class ExamResults:
    exam: Exam
    questions: list[Question]
    scripts: list[ScriptResult]
    review_times: dict[int, ReviewTime]

    @property
    def confirmed(self) -> list[ScriptResult]:
        return [s for s in self.scripts if s.confirmed]

    def question_average_half(self, question_id: int) -> float | None:
        marks = [
            q.final_half
            for s in self.confirmed
            for q in s.questions
            if q.question.id == question_id and q.final_half is not None
        ]
        return sum(marks) / len(marks) if marks else None

    @property
    def average_total_half(self) -> float | None:
        totals = [s.total_half for s in self.confirmed if s.total_half is not None]
        return sum(totals) / len(totals) if totals else None


def exam_results(db: Session, actor: User, exam_id: int) -> ExamResults:
    exam = get_visible_exam(db, actor, exam_id)
    scripts = list(db.scalars(select(Script).where(Script.exam_id == exam.id)))
    return ExamResults(
        exam,
        exam_questions(db, exam.id),
        script_results(db, exam, scripts),
        review_times(db, [s.id for s in scripts]),
    )
