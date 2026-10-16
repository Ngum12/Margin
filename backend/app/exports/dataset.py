"""Anonymous correction statistics. Raw handwriting and free text stay on the school box."""

import json
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Exam, RemarkRequest, Script
from app.services.decisions import current_decisions
from app.services.results import script_results

FORMAT_VERSION = 2
MIN_STUDENTS = 5
README = """# Margin anonymous correction statistics

Format version 2. School opt-in and individual training consent are required.
Only teacher-confirmed scripts contribute. Groups with fewer than five distinct
consenting students are suppressed. No person, school, exam identifiers, dates,
images, handwriting, transcriptions, question wording, comments or model free text
are exported. No automatic transmission occurs.

Files: `dataset.jsonl` contains aggregate rows; `manifest.json` identifies the format.
Each row has `format_version` and `kind` (point or remark).
Point rows: `max_marks`, `category`, `count`, `mean_proposed_marks`,
`mean_final_marks`, `correction_count`.
Remark rows: `reason`, `count`, `changed_count`, `mean_change`.

These aggregates support correction analysis and calibration. Consented source
records remain local for future school-side fine-tuning; this archive contains
no handwriting training examples. Do not combine aggregates with external
student-level records. Consent is checked again when the export is built.
"""


@dataclass(frozen=True)
class DatasetCounts:
    exams: int
    scripts: int
    pages: int


def write_dataset(
    db: Session, exams: list[tuple[Exam, list[Script]]], data_dir: Path, out: Path
) -> DatasetCounts:
    groups: dict[tuple[int, str], list[tuple[int, int, int]]] = defaultdict(list)
    remark_groups: dict[str, list[tuple[int, bool, float]]] = defaultdict(list)
    scripts_done = 0
    for exam, scripts in exams:
        decisions = current_decisions(db, [s.id for s in scripts])
        for result in script_results(db, exam, scripts):
            scripts_done += 1
            for q in result.questions:
                for p in q.points:
                    decision = decisions.get((result.script.id, p.point_id))
                    if (
                        decision is None
                        or decision.proposed_half_marks is None
                        or p.final_half is None
                    ):
                        continue
                    category = p.final_category.value if p.final_category else "omitted"
                    groups[p.max_half, category].append(
                        (result.script.student_id, decision.proposed_half_marks, p.final_half)
                    )
        for remark in db.scalars(
            select(RemarkRequest).where(
                RemarkRequest.script_id.in_([s.id for s in scripts]),
                RemarkRequest.status == "answered",
            )
        ):
            if remark.reason not in {"missing_mark", "total_error", "unmarked_answer", "other"}:
                continue
            replies = [r for r in remark.responses if not r.get("automatic")]
            delta = sum(
                float(r.get("new_marks", 0)) - float(r.get("old_marks", 0)) for r in replies
            )
            remark_groups[remark.reason].append(
                (remark.student_id, any(bool(r.get("changed")) for r in replies), delta)
            )
    lines: list[dict[str, Any]] = []
    for (maximum, category), values in sorted(groups.items()):
        if len({v[0] for v in values}) < MIN_STUDENTS:
            continue
        lines.append(
            {
                "format_version": FORMAT_VERSION,
                "kind": "point",
                "max_marks": maximum / 2,
                "category": category,
                "count": len(values),
                "mean_proposed_marks": sum(v[1] for v in values) / len(values) / 2,
                "mean_final_marks": sum(v[2] for v in values) / len(values) / 2,
                "correction_count": sum(v[1] != v[2] for v in values),
            }
        )
    for reason, remark_values in sorted(remark_groups.items()):
        if len({v[0] for v in remark_values}) < MIN_STUDENTS:
            continue
        lines.append(
            {
                "format_version": FORMAT_VERSION,
                "kind": "remark",
                "reason": reason,
                "count": len(remark_values),
                "changed_count": sum(v[1] for v in remark_values),
                "mean_change": sum(v[2] for v in remark_values) / len(remark_values),
            }
        )
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dataset.jsonl", "".join(json.dumps(line) + "\n" for line in lines))
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format_version": FORMAT_VERSION,
                    "minimum_students": MIN_STUDENTS,
                    "groups": len(lines),
                }
            ),
        )
        archive.writestr("README.md", README)
    return DatasetCounts(sum(bool(s) for _, s in exams), scripts_done, 0)
