"""One scoring rule implementation for review, results and printed copies."""

from collections.abc import Mapping

from app.db.models import Question
from app.schemas.mark_scheme import PointGroup, PointRules


def score_question(question: Question, awarded: Mapping[int, int | None]) -> int | None:
    if not any(awarded.get(p.id) is not None for p in question.points):
        return None
    rules = {p.id: PointRules.model_validate(p.rules or {}) for p in question.points}
    keyed = {rules[p.id].key: p for p in question.points if rules[p.id].key}
    resolved: dict[int, int] = {}

    def value(point_id: int, visiting: frozenset[int] = frozenset()) -> int:
        if point_id in resolved:
            return resolved[point_id]
        if point_id in visiting:
            return 0  # Invalid legacy data must not create marks.
        rule = rules[point_id]
        for dependency in rule.depends_on:
            required = keyed.get(dependency)
            if required is None or value(required.id, visiting | {point_id}) < required.half_marks:
                resolved[point_id] = 0
                return 0
        point = next(p for p in question.points if p.id == point_id)
        resolved[point_id] = max(0, min(awarded.get(point_id) or 0, point.half_marks))
        return resolved[point_id]

    total = sum(value(p.id) for p in question.points if not rules[p.id].group)
    for raw in question.groups or []:
        group = PointGroup.model_validate(raw)
        values = sorted(
            (value(p.id) for p in question.points if rules[p.id].group == group.key), reverse=True
        )
        total += min(sum(values[: group.max_points]), group.max_marks * 2)
    return min(total, question.max_half_marks)
