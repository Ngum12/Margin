"""Mark scheme validation rules (D-014). Pure functions, no database.

Issues come in three groups:
- ``blocking``: the scheme cannot be saved at all (it would break data integrity).
- ``readiness``: the scheme can be saved as a draft but the exam cannot be marked ready.
- ``notices``: information for the teacher; never blocks anything.
"""

import re
from dataclasses import dataclass, field

from app.errors import Issue
from app.schemas.mark_scheme import MarkSchemeIn, QuestionIn

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

        points_total = validate_rules(question, qi, report)
        if question.label and not re.fullmatch(
            r"[1-9][0-9]*(?:\((?:[a-zA-Z]+|[0-9]+)\))*", question.label
        ):
            report.notices.append(Issue("scheme.numbering", qpath))
        if question.points and points_valid and question.max_marks >= 1:
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


def validate_rules(question: QuestionIn, qi: int, report: MarkSchemeReport) -> int:
    """Validate references before scoring; return attainable grouped whole marks."""
    path: list[str | int] = ["questions", qi]
    keys = [p.rules.key for p in question.points if p.rules.key]
    groups = {g.key: g for g in question.groups}
    invalid = len(keys) != len(set(keys)) or len(groups) != len(question.groups)
    by_key = {p.rules.key: p for p in question.points if p.rules.key}
    for point in question.points:
        rule = point.rules
        if rule.group and rule.group not in groups:
            invalid = True
        if rule.kind == "A" and not rule.depends_on:
            invalid = True
        if any(k not in by_key for k in rule.depends_on):
            invalid = True
        if rule.kind == "A" and not any(
            by_key[k].rules.kind == "M" for k in rule.depends_on if k in by_key
        ):
            invalid = True

    checked: set[str] = set()

    def cyclic(key: str, visiting: frozenset[str]) -> bool:
        if key in visiting:
            return True
        if key in checked:
            return False
        point = by_key.get(key)
        result = bool(point and any(cyclic(k, visiting | {key}) for k in point.rules.depends_on))
        checked.add(key)
        return result

    if any(cyclic(key, frozenset()) for key in by_key):
        invalid = True
    total = sum(p.marks for p in question.points if not p.rules.group)
    for group in question.groups:
        members = sorted(
            (p.marks for p in question.points if p.rules.group == group.key), reverse=True
        )
        if len(members) < group.max_points or sum(members[: group.max_points]) < group.max_marks:
            invalid = True
        total += min(sum(members[: group.max_points]), group.max_marks)
    if invalid:
        report.blocking.append(Issue("scheme.rules_invalid", path))
    return total
