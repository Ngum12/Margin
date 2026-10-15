"""Training-data export (brief section 8): a zip with page images, ``dataset.jsonl`` and a README.

Only confirmed scripts of students with training consent. Pseudonymous codes only: no names, and
no teacher comments (free text that could mention a name). Images are written upright.
"""

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from app.db.models import Exam, MarkDecision, School, Script, TranscriptionSource
from app.marks import from_half_marks
from app.services import transcripts
from app.services.decisions import current_decisions
from app.services.results import script_results

FORMAT_VERSION = 1

README = """# Margin training dataset

Produced by Margin's training-data export (format version {version}). It contains only scripts
that a teacher confirmed, of students whose training consent was recorded, from {school_count}
school installation(s).

## Privacy
- Students appear only by their pseudonymous code. No names are included.
- Teacher comments are not included.
- Page images and transcriptions show whatever students wrote. Check them before sharing
  outside the school, in case a student wrote a name on an answer page.

## Files
- `dataset.jsonl`: one JSON object per script (fields below).
- `images/`: page images, turned upright, named `<exam id>_<student code>_p<page>.jpg`.

## Fields of each line in `dataset.jsonl`
- `format_version`: this format's version ({version}).
- `exam`: `id`, `title`, `subject`, `curriculum`, `date`.
- `student_code`: the student's pseudonymous code.
- `pages`: in order; each has `image` (path in this zip), `is_cover`, `transcription` (the final
  text: the newest version, by a teacher or the model), `transcription_source` (`model` or
  `teacher`), `reader_model`, `reader_model_version`, `reader_prompt_version` (of the model's
  latest read of that page, if any).
- `questions`: in order; each has `label`, `prompt`, `max_marks` and `points`. Each point has
  `description`, `alternatives`, `max_marks`, `final_marks` and `final_category` (the teacher's
  decision), and `proposal`: the model's original proposal (`marks`, `evidence`, `confidence`,
  `category`, `model`, `model_version`, `prompt_version`), or null if the model made none.
- `question_marks`: the final mark per question (capped at its maximum), and `total`/`max_total`.

Error categories: `correct`, `conceptual_error`, `language_expression`,
`transcription_uncertain`, `omitted`.
"""


@dataclass(frozen=True)
class DatasetCounts:
    exams: int
    scripts: int
    pages: int


def _upright_jpeg(path: Path, rotation: int) -> bytes:
    if rotation % 360 == 0:
        return path.read_bytes()
    with Image.open(path) as source:
        image = source.convert("RGB").rotate(-(rotation % 360), expand=True)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=90)
        return buffer.getvalue()


def _proposal(decision: MarkDecision | None) -> dict[str, Any] | None:
    if decision is None or decision.proposed_half_marks is None:
        return None
    return {
        "marks": from_half_marks(decision.proposed_half_marks),
        "evidence": decision.evidence,
        "confidence": decision.confidence,
        "category": decision.error_category.value if decision.error_category else None,
        "model": decision.model_name,
        "model_version": decision.model_version,
        "prompt_version": decision.prompt_version,
    }


def write_dataset(
    db: Session, exams: list[tuple[Exam, list[Script]]], data_dir: Path, out: Path
) -> DatasetCounts:
    scripts_done = pages_done = 0
    schools: set[int] = set()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        lines = []
        for exam, scripts in exams:
            school = exam.school_class.school_id
            schools.add(school)
            curriculum = db.get(School, school)
            decisions = current_decisions(db, [s.id for s in scripts])
            for result in script_results(db, exam, scripts, with_pages=True):
                code = result.script.student.code
                pages = []
                for number, result_page in enumerate(result.pages, 1):
                    page = result_page.page
                    name = f"images/{exam.id}_{code}_p{number}.jpg"
                    archive.writestr(
                        name, _upright_jpeg(data_dir / page.image_path, page.effective_rotation)
                    )
                    versions = transcripts.page_versions(db, page.id)
                    final = transcripts.current(versions)
                    model_reads = [v for v in versions if v.source == TranscriptionSource.MODEL]
                    read = model_reads[-1] if model_reads else None
                    pages.append(
                        {
                            "image": name,
                            "is_cover": page.is_cover,
                            "transcription": final.text if final else None,
                            "transcription_source": final.source.value if final else None,
                            "reader_model": read.model_name if read else None,
                            "reader_model_version": read.model_version if read else None,
                            "reader_prompt_version": read.prompt_version if read else None,
                        }
                    )
                    pages_done += 1
                questions = []
                for question in result.questions:
                    alternatives = {p.id: p.alternatives for p in question.question.points}
                    questions.append(
                        {
                            "label": question.question.label,
                            "prompt": question.question.prompt_text,
                            "max_marks": from_half_marks(question.question.max_half_marks),
                            "points": [
                                {
                                    "description": point.description,
                                    "alternatives": list(alternatives.get(point.point_id) or []),
                                    "max_marks": from_half_marks(point.max_half),
                                    "final_marks": (
                                        None
                                        if point.final_half is None
                                        else from_half_marks(point.final_half)
                                    ),
                                    "final_category": (
                                        point.final_category.value if point.final_category else None
                                    ),
                                    "proposal": _proposal(
                                        decisions.get((result.script.id, point.point_id))
                                    ),
                                }
                                for point in question.points
                            ],
                        }
                    )
                lines.append(
                    {
                        "format_version": FORMAT_VERSION,
                        "exam": {
                            "id": exam.id,
                            "title": exam.title,
                            "subject": exam.subject_code,
                            "curriculum": curriculum.curriculum if curriculum else None,
                            "date": exam.exam_date.isoformat() if exam.exam_date else None,
                        },
                        "student_code": code,
                        "pages": pages,
                        "questions": questions,
                        "question_marks": {
                            q.question.label: (
                                None if q.final_half is None else from_half_marks(q.final_half)
                            )
                            for q in result.questions
                        },
                        "total": from_half_marks(result.total_half or 0),
                        "max_total": from_half_marks(result.max_half),
                    }
                )
                scripts_done += 1
        archive.writestr(
            "dataset.jsonl",
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
        )
        archive.writestr(
            "README.md", README.format(version=FORMAT_VERSION, school_count=len(schools) or 1)
        )
    return DatasetCounts(sum(1 for _e, s in exams if s), scripts_done, pages_done)
