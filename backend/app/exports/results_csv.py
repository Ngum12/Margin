"""Results CSV: one row per confirmed script, one column per question."""

import csv
import io

from app.db.models import Question
from app.exports.labels import labels
from app.marks import from_half_marks
from app.services.results import ScriptResult

# Spreadsheets run cells that start with these as formulas (CSV injection).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_START) else value


def results_csv(questions: list[Question], scripts: list[ScriptResult], language: str) -> bytes:
    """UTF-8 with a byte-order mark so spreadsheet programs show accents correctly."""
    words = labels(language)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        [
            words["student_code"],
            words["student_name"],
            *(_safe(q.label) for q in questions),
            words["total"],
            words["max"],
            words["percentage"],
            words["confirmed_at"],
            words["ai_model"],
        ]
    )
    for result in scripts:
        total = result.total_half or 0
        writer.writerow(
            [
                _safe(result.script.student.code),
                _safe(result.script.student.display_name or ""),
                *(
                    "" if q.final_half is None else from_half_marks(q.final_half)
                    for q in result.questions
                ),
                from_half_marks(total),
                from_half_marks(result.max_half),
                round(100 * total / result.max_half, 1) if result.max_half else "",
                result.confirmed_at.isoformat(timespec="minutes") if result.confirmed_at else "",
                words["test_model"] if result.test_model else ", ".join(result.models),
            ]
        )
    return ("﻿" + buffer.getvalue()).encode("utf-8")
