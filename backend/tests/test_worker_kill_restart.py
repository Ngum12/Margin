"""Brief section 9, Phase 3: killing the worker mid-run and restarting it completes the run with
no duplicated results. The worker runs as a real separate process and is killed abruptly."""

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.config import Settings
from app.db.models import MarkDecision, Script, ScriptStatus, Transcription
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, start_ai, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages

BACKEND_DIR = Path(__file__).resolve().parents[1]
CODES = ("AAAAAA", "BBBBBB", "CCCCCC")
PAGES_PER_SCRIPT = 3


def _start_worker(settings: Settings, log: BinaryIO) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "MARGIN_DATA_DIR": str(settings.data_dir),
        "MARGIN_ENV": "test",
        "MARGIN_AI_BACKEND": "mock",
        "MARGIN_MOCK_DELAY_SECONDS": "0.7",  # slow enough to kill it mid-run
        "MARGIN_WORKER_POLL_SECONDS": "0.2",
        "MARGIN_JOB_STALE_SECONDS": "2",
    }
    return subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        cwd=BACKEND_DIR,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def _wait_for(condition: Callable[[], bool], timeout: float, log: Path) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.2)
    tail = log.read_text(encoding="utf-8", errors="replace")[-3000:] if log.exists() else ""
    raise AssertionError("timed out; worker output:\n" + tail)


def _count(app: FastAPI, model: Any) -> int:
    with app.state.sessionmaker() as db:
        return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _all_marked(app: FastAPI) -> bool:
    with app.state.sessionmaker() as db:
        return all(st == ScriptStatus.AI_MARKED for st in db.scalars(select(Script.status)))


@pytest.fixture
def queued_exam(app: FastAPI, world: World, factory: Factory) -> dict[str, Any]:
    alice = ApiUser(app, "alice")
    for code in CODES:
        factory.student(world.class_a, code)
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    scan = ScanBuilder()
    for i, cover in enumerate(covers):
        scan.add(cover)
        for k in range(PAGES_PER_SCRIPT):
            scan.add(answer_page(10 * i + k))
    upload_pdf(alice, exam["id"], scan.build())  # processed in-process
    assert start_ai(alice, exam["id"]).status_code == 202
    return exam


def test_killed_worker_resumes_without_duplicates(
    app: FastAPI, queued_exam: dict[str, Any], settings: Settings, tmp_path: Path
) -> None:
    total_pages = PAGES_PER_SCRIPT * len(CODES)
    total_points = 3 * len(CODES)
    log = tmp_path / "worker.log"

    with log.open("ab") as log_file:
        first = _start_worker(settings, log_file)
        try:
            _wait_for(lambda: _count(app, Transcription) >= 2, timeout=60, log=log)
        finally:
            first.kill()  # abrupt, like a power cut
            first.wait(timeout=10)

        done_before = _count(app, Transcription)
        assert 0 < done_before < total_pages, "the kill should land mid-run"
        with app.state.sessionmaker() as db:
            kept = {t.id: t.created_at for t in db.scalars(select(Transcription))}

        second = _start_worker(settings, log_file)
        try:
            _wait_for(
                lambda: _count(app, MarkDecision) == total_points and _all_marked(app),
                timeout=120,
                log=log,
            )
        finally:
            second.terminate()
            second.wait(timeout=10)

    with app.state.sessionmaker() as db:
        transcriptions = db.scalars(select(Transcription)).all()
        decisions = db.scalars(select(MarkDecision)).all()
    assert len(transcriptions) == total_pages
    assert len({t.page_id for t in transcriptions}) == total_pages  # no page twice
    assert len(decisions) == total_points
    assert len({(d.script_id, d.mark_scheme_point_id) for d in decisions}) == total_points
    # Pages finished before the kill were kept, not redone.
    after = {t.id: t.created_at for t in transcriptions}
    assert all(after[i] == created for i, created in kept.items())
