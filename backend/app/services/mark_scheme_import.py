"""Parse a mark scheme CSV into ``MarkSchemeIn``. Input is untrusted: sizes are bounded and
every problem is reported per row with a stable code, never guessed around.

Format: one row per mark scheme point; question columns repeat on each row of that question.

    question_label,question_prompt,question_max_marks,point_description,point_marks,point_alternatives
    1(a),State two properties of metals,2,Conducts electricity,1,conductor|good conductor
    1(a),State two properties of metals,2,Malleable,1,
"""

import csv
import io
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.errors import Issue
from app.schemas.mark_scheme import MarkSchemeIn, PointIn, QuestionIn

MAX_CSV_BYTES = 1024 * 1024
MAX_CSV_ROWS = 5000

REQUIRED_COLUMNS = (
    "question_label",
    "question_prompt",
    "question_max_marks",
    "point_description",
    "point_marks",
)
OPTIONAL_COLUMNS = ("point_alternatives",)
ALTERNATIVES_SEPARATOR = "|"


@dataclass
class ImportResult:
    scheme: MarkSchemeIn | None
    issues: list[Issue] = field(default_factory=list)


def _row_issue(code: str, row: int, **params: object) -> Issue:
    return Issue(code, ["row", row], dict(params))


def _parse_whole_number(value: str) -> int | None:
    value = value.strip()
    if not value or not value.lstrip("-").isdigit():
        return None
    return int(value)


def decode_csv(data: bytes) -> str | Issue:
    if len(data) > MAX_CSV_BYTES:
        return Issue("import.too_large", params={"max_kb": MAX_CSV_BYTES // 1024})
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return Issue("import.not_utf8")


def parse_mark_scheme_csv(text: str) -> ImportResult:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        return ImportResult(None, [Issue("import.missing_columns", params={"columns": missing})])
    reader.fieldnames = header

    questions: list[QuestionIn] = []
    by_label: dict[str, tuple[int, QuestionIn, int]] = {}  # label -> (index, question, first row)
    issues: list[Issue] = []

    try:
        for row_number, raw in enumerate(reader, start=2):  # row 1 is the header
            if row_number - 1 > MAX_CSV_ROWS:
                return ImportResult(
                    None, [Issue("import.too_many_rows", params={"max": MAX_CSV_ROWS})]
                )
            if None in raw:  # more cells than headers
                issues.append(_row_issue("import.row_extra_cells", row_number))
                continue
            row = {k: (v or "").strip() for k, v in raw.items()}
            if not any(row.values()):
                continue

            label = row["question_label"]
            if not label:
                issues.append(_row_issue("import.label_required", row_number))
                continue
            max_marks = _parse_whole_number(row["question_max_marks"])
            point_marks = _parse_whole_number(row["point_marks"])
            if max_marks is None:
                issues.append(_row_issue("import.max_marks_not_number", row_number))
            if point_marks is None:
                issues.append(_row_issue("import.point_marks_not_number", row_number))
            if max_marks is None or point_marks is None:
                continue

            alternatives = [
                a.strip()
                for a in row.get("point_alternatives", "").split(ALTERNATIVES_SEPARATOR)
                if a.strip()
            ]
            try:
                point = PointIn(
                    description=row["point_description"],
                    marks=point_marks,
                    alternatives=alternatives,
                )
            except ValidationError:
                issues.append(_row_issue("import.row_invalid", row_number))
                continue

            key = label.casefold()
            if key in by_label:
                index, question, first_row = by_label[key]
                if index != len(questions) - 1:
                    issues.append(
                        _row_issue("import.question_not_contiguous", row_number, label=label)
                    )
                    continue
                if (
                    question.max_marks != max_marks
                    or question.prompt_text != row["question_prompt"]
                ):
                    issues.append(
                        _row_issue(
                            "import.question_inconsistent",
                            row_number,
                            label=label,
                            first_row=first_row,
                        )
                    )
                    continue
                question.points.append(point)
            else:
                try:
                    question = QuestionIn(
                        label=label,
                        prompt_text=row["question_prompt"],
                        max_marks=max_marks,
                        points=[point],
                    )
                except ValidationError:
                    issues.append(_row_issue("import.row_invalid", row_number))
                    continue
                by_label[key] = (len(questions), question, row_number)
                questions.append(question)
    except csv.Error:
        return ImportResult(None, [Issue("import.malformed_csv")])

    if issues:
        return ImportResult(None, issues)
    if not questions:
        return ImportResult(None, [Issue("import.empty")])
    return ImportResult(MarkSchemeIn(questions=questions))
