#!/usr/bin/env python3
"""Start the real app on a fresh, seeded database for the browser tests (Phase 4).

Run from ``backend/`` (Playwright does this):  uv run python ../scripts/e2e_server.py --port 8765

Seed: one school, teachers alice (Form 5A) and bruno (Form 5B), a ready chemistry exam with
three scripts uploaded and marked by the Mock models:
- AAAAAA "Ama Fon": a normal script for the keyboard-only review;
- BBBBBB "Bih Ndi": its answer page was turned 180 degrees automatically, and the AI deducted a
  mark on one point (rotation, undo and French scenarios);
- CCCCCC: flagged for manual marking, no AI proposals.
Everything stays in a temporary folder on this computer; nothing is sent anywhere.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import warnings
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
# Same filter as the backend tests (D-010): the seed uses Starlette's TestClient.
warnings.filterwarnings("ignore", message=".*httpx2.*")

import uvicorn  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import MarkDecision, Page, Role, Script, Student  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, upload_pdf  # noqa: E402
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages  # noqa: E402

STUDENTS = (("AAAAAA", "Ama Fon"), ("BBBBBB", "Bih Ndi"), ("CCCCCC", None))


def seed(settings: Settings) -> None:
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.sessionmaker() as db:
        factory = Factory(db)
        school = factory.school()
        factory.user(school, "admin", Role.ADMIN)
        alice = factory.user(school, "alice")
        bruno = factory.user(school, "bruno")
        class_a = factory.school_class(school, alice, "Form 5A")
        factory.school_class(school, bruno, "Form 5B")
        for code, name in STUDENTS:
            factory.student(class_a, code, name)
        class_id = class_a.id

    teacher = ApiUser(app, "alice")
    exam = make_ready_exam(teacher, class_id, "Mock exam 1")
    teacher.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(teacher.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    scan = ScanBuilder()
    for index, cover in enumerate(covers):
        scan.add(cover).add(answer_page(index))
    upload_pdf(teacher, exam["id"], scan.build())
    teacher.post(f"/api/exams/{exam['id']}/ai-marking")
    run_jobs(app)

    with app.state.sessionmaker() as db:
        scripts = {
            code: script
            for script, code in db.execute(
                select(Script, Student.code).join(Student, Script.student_id == Student.id)
            ).all()
        }
        turned = db.scalars(
            select(Page).where(Page.script_id == scripts["BBBBBB"].id, Page.is_cover.is_(False))
        ).one()
        turned.rotation_auto, turned.auto_rotation_confidence = 180, 0.95
        deducted = db.scalars(
            select(MarkDecision)
            .where(MarkDecision.script_id == scripts["BBBBBB"].id)
            .order_by(MarkDecision.id)
        ).first()
        if deducted is not None:
            deducted.proposed_half_marks = 0
        manual = scripts["CCCCCC"]
        db.execute(delete(MarkDecision).where(MarkDecision.script_id == manual.id))
        manual.manual_reason = "ai.marker_invalid_output"
        db.commit()
    app.state.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()

    data_dir = args.data_dir or Path(tempfile.mkdtemp(prefix="margin-e2e-")) / "data"
    settings = Settings(_env_file=None, env="test", data_dir=data_dir, ai_backend="mock")
    if not (settings.frontend_dist / "index.html").is_file():
        sys.exit("error: frontend/dist is missing; run `npm run build` in frontend/ first")
    seed(settings)
    print(f"e2e: seeded {data_dir}; serving on http://127.0.0.1:{args.port}", flush=True)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
