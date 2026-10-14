"""Mark scheme validation rules (D-014). Pure functions, no database.

Issues come in three groups:
- ``blocking``: the scheme cannot be saved at all (it would break data integrity).
- ``readiness``: the scheme can be saved as a draft but the exam cannot be marked ready.
- ``notices``: information for the teacher; never blocks anything.
"""

from dataclasses import dataclass, field

from app.errors import Issue
from app.schemas.mark_scheme import MarkSchemeIn

MAX_LABEL_LENGTH = 20
MAX_MARKS_PER_ITEM = 100
MAX_QUESTIONS = 100
MAX_POINTS_PER_QUESTION = 50


@dataclass
class MarkSchemeReport:
    blocking: list[Issue] = field(default_factory=list)
    readiness: list[Issue] = field(default_factory=list)
    notices: list[Issue] = field(default_factory=list)

    @property
    def can_save(self) -> bool:
        return not self.blocking

    @property
    def is_ready(self) -> bool:
        return not self.blocking and not self.readiness


def total_marks(scheme: MarkSchemeIn) -> int:
    return sum(q.max_marks for q in scheme.questions)


def validate_mark_scheme(scheme: MarkSchemeIn) -> MarkSchemeReport:
    report = MarkSchemeReport()

    if not scheme.questions:
        report.readiness.append(Issue("exam.no_questions"))
    if len(scheme.questions) > MAX_QUESTIONS:
        report.blocking.append(Issue("exam.too_many_questions", params={"max": MAX_QUESTIONS}))

    seen_labels: dict[str, int] = {}
    for qi, question in enumerate(scheme.questions):
        qpath: list[str | int] = ["questions", qi]
        label_key = question.label.casefold()

        if not question.label:
            report.blocking.append(Issue("question.label_required", [*qpath, "label"]))
        elif len(question.label) > MAX_LABEL_LENGTH:
            report.blocking.append(
                Issue("question.label_too_long", [*qpath, "label"], {"max": MAX_LABEL_LENGTH})
            )
        elif label_key in seen_labels:
            report.blocking.append(
                Issue(
                    "question.label_duplicate",
                    [*qpath, "label"],
                    {"label": question.label, "first": seen_labels[label_key] + 1},
                )
            )
        else:
            seen_labels[label_key] = qi

        if not 1 <= question.max_marks <= MAX_MARKS_PER_ITEM:
            report.blocking.append(
                Issue(
                    "question.max_marks_invalid", [*qpath, "max_marks"], {"max": MAX_MARKS_PER_ITEM}
                )
            )

        if len(question.points) > MAX_POINTS_PER_QUESTION:
            report.blocking.append(
                Issue("question.too_many_points", qpath, {"max": MAX_POINTS_PER_QUESTION})
            )
        if not question.points:
            report.readiness.append(Issue("question.no_points", qpath, {"label": question.label}))

        points_valid = True
        for pi, point in enumerate(question.points):
            ppath: list[str | int] = [*qpath, "points", pi]
            if not 1 <= point.marks <= MAX_MARKS_PER_ITEM:
                points_valid = False
                report.blocking.append(
                    Issue("point.marks_invalid", [*ppath, "marks"], {"max": MAX_MARKS_PER_ITEM})
                )
            if not point.description:
                report.readiness.append(
                    Issue("point.description_required", [*ppath, "description"])
                )

        if question.points and points_valid and question.max_marks >= 1:
            points_total = sum(p.marks for p in question.points)
            params = {
                "label": question.label,
                "points_total": points_total,
                "max_marks": question.max_marks,
            }
            if points_total < question.max_marks:
                report.readiness.append(Issue("question.points_below_max", qpath, params))
            elif points_total > question.max_marks:
                report.notices.append(Issue("question.points_exceed_max", qpath, params))

    return report
