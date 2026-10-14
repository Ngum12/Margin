"""Upload storage, validation, permissions, and isolation of the render worker."""

import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Page, Upload
from app.pdf import runner
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def exam(alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    factory.student(world.class_a, "AAAAAA")
    return make_ready_exam(alice, world.class_a.id)


@pytest.fixture
def small_pdf() -> bytes:
    return ScanBuilder().add(answer_page(1)).add(answer_page(2)).build()


def test_original_is_stored_unchanged_with_checksum(
    alice: ApiUser, exam: dict[str, Any], small_pdf: bytes, settings: Settings, db: Session
) -> None:
    response = upload_pdf(alice, exam["id"], small_pdf, "Form 5A — batch 1.pdf")

    assert response.status_code == 202
    body = response.json()
    upload = db.get(Upload, body["id"])
    assert upload is not None
    stored = (settings.data_dir / upload.stored_path).read_bytes()
    assert stored == small_pdf
    assert upload.sha256 == hashlib.sha256(small_pdf).hexdigest() == body["sha256"]
    assert upload.size_bytes == len(small_pdf)
    assert upload.original_filename == "Form 5A — batch 1.pdf"


def test_original_can_be_downloaded_identically(
    alice: ApiUser, exam: dict[str, Any], small_pdf: bytes
) -> None:
    upload = upload_pdf(alice, exam["id"], small_pdf).json()

    response = alice.get(f"/api/uploads/{upload['id']}/original")

    assert response.status_code == 200
    assert response.content == small_pdf


def test_upload_is_processed_into_page_images(
    alice: ApiUser, exam: dict[str, Any], small_pdf: bytes, db: Session, settings: Settings
) -> None:
    upload_pdf(alice, exam["id"], small_pdf)

    uploads = alice.get(f"/api/exams/{exam['id']}/uploads").json()
    assert uploads[0]["status"] == "processed"
    assert uploads[0]["page_count"] == 2
    pages = db.scalars(select(Page).order_by(Page.source_page_index)).all()
    assert len(pages) == 2
    for page in pages:
        assert (settings.data_dir / page.image_path).is_file()
        assert (settings.data_dir / page.thumb_path).is_file()
        # 200 dpi A4
        assert (page.width, page.height) == (1654, 2339)


def test_same_file_twice_is_refused(alice: ApiUser, exam: dict[str, Any], small_pdf: bytes) -> None:
    upload_pdf(alice, exam["id"], small_pdf)

    response = upload_pdf(alice, exam["id"], small_pdf)

    assert response.status_code == 409
    assert response.json()["code"] == "upload.duplicate_file"


def test_non_pdf_is_refused(alice: ApiUser, exam: dict[str, Any], settings: Settings) -> None:
    response = upload_pdf(alice, exam["id"], b"GIF89a not a pdf")

    assert response.status_code == 422
    assert response.json()["code"] == "upload.not_pdf"
    assert list((settings.upload_dir / "incoming").iterdir()) == []


def test_wrong_content_type_is_refused(alice: ApiUser, exam: dict[str, Any]) -> None:
    response = alice.post(
        f"/api/exams/{exam['id']}/uploads",
        content=b"%PDF-1.7",
        headers={"Content-Type": "text/plain"},
    )

    assert response.json()["code"] == "upload.not_pdf"


def test_too_large_is_refused(
    app: FastAPI, alice: ApiUser, exam: dict[str, Any], settings: Settings
) -> None:
    app.state.settings = settings.model_copy(update={"max_upload_mb": 1})

    response = upload_pdf(alice, exam["id"], b"%PDF-1.7\n" + b"0" * (1024 * 1024 + 10))

    assert response.status_code == 413
    assert response.json()["code"] == "upload.too_large"


def test_draft_exam_refuses_uploads(alice: ApiUser, world: World, small_pdf: bytes) -> None:
    exam = alice.post(
        "/api/exams", json={"class_id": world.class_a.id, "subject_code": "chemistry", "title": "D"}
    ).json()

    assert upload_pdf(alice, exam["id"], small_pdf).status_code == 409


def test_other_teacher_cannot_upload_or_see_scans(
    app: FastAPI, alice: ApiUser, exam: dict[str, Any], small_pdf: bytes, db: Session
) -> None:
    upload = upload_pdf(alice, exam["id"], small_pdf).json()
    page_id = db.scalars(select(Page.id)).first()
    bruno = ApiUser(app, "bruno")

    assert upload_pdf(bruno, exam["id"], b"%PDF-1.7 other").status_code == 404
    assert bruno.get(f"/api/exams/{exam['id']}/uploads").status_code == 404
    assert bruno.get(f"/api/uploads/{upload['id']}/original").status_code == 404
    assert bruno.get(f"/api/pages/{page_id}/image").status_code == 404


def test_page_images_need_sign_in(
    app: FastAPI, alice: ApiUser, exam: dict[str, Any], small_pdf: bytes, db: Session
) -> None:
    from fastapi.testclient import TestClient

    upload_pdf(alice, exam["id"], small_pdf)
    page_id = db.scalars(select(Page.id)).first()

    assert TestClient(app).get(f"/api/pages/{page_id}/image").status_code == 401
    full = alice.get(f"/api/pages/{page_id}/image")
    thumb = alice.get(f"/api/pages/{page_id}/image?size=thumb")
    assert full.headers["content-type"] == "image/jpeg"
    assert len(thumb.content) < len(full.content)


def test_files_are_not_served_publicly(
    alice: ApiUser, exam: dict[str, Any], small_pdf: bytes, app: FastAPI
) -> None:
    from fastapi.testclient import TestClient

    upload = upload_pdf(alice, exam["id"], small_pdf).json()
    anonymous = TestClient(app)

    for path in [
        f"/uploads/{upload['id']}/original.pdf",
        f"/data/uploads/{upload['id']}/original.pdf",
    ]:
        response = anonymous.get(path)
        assert b"%PDF" not in response.content


# --- worker isolation (D-028) -------------------------------------------------------------------


def test_malformed_pdf_fails_cleanly_and_server_keeps_working(
    alice: ApiUser, exam: dict[str, Any]
) -> None:
    malformed = (
        b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >>\nendobj\ntrailer garbage \x00\xff"
    )

    response = upload_pdf(alice, exam["id"], malformed)

    assert response.status_code == 202
    upload = alice.get(f"/api/exams/{exam['id']}/uploads").json()[0]
    assert upload["status"] == "failed"
    assert upload["error_code"] == "upload.pdf_unreadable"
    assert alice.get("/api/health").json()["status"] == "ok"


def test_hanging_worker_is_killed_after_timeout(
    app: FastAPI,
    alice: ApiUser,
    exam: dict[str, Any],
    small_pdf: bytes,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fast = settings.model_copy(update={"render_timeout_seconds": 1})
    app.state.upload_processor._settings = fast
    monkeypatch.setattr(
        runner,
        "worker_command",
        lambda *_args: [sys.executable, "-c", "import time; time.sleep(60)"],
    )

    upload_pdf(alice, exam["id"], small_pdf)

    upload = alice.get(f"/api/exams/{exam['id']}/uploads").json()[0]
    assert upload["status"] == "failed"
    assert upload["error_code"] == "upload.render_timeout"
    assert alice.get("/api/health").status_code == 200


def test_crashing_worker_fails_the_upload_not_the_server(
    alice: ApiUser,
    exam: dict[str, Any],
    small_pdf: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner, "worker_command", lambda *_args: [sys.executable, "-c", "import os; os.abort()"]
    )

    upload_pdf(alice, exam["id"], small_pdf)

    upload = alice.get(f"/api/exams/{exam['id']}/uploads").json()[0]
    assert upload["error_code"] == "upload.render_crashed"
    assert alice.get("/api/health").status_code == 200


def test_too_many_pages_is_reported(
    app: FastAPI, alice: ApiUser, exam: dict[str, Any], small_pdf: bytes, settings: Settings
) -> None:
    app.state.upload_processor._settings = settings.model_copy(update={"max_pdf_pages": 1})

    upload_pdf(alice, exam["id"], small_pdf)

    assert (
        alice.get(f"/api/exams/{exam['id']}/uploads").json()[0]["error_code"]
        == "upload.too_many_pages"
    )


def test_failed_upload_can_be_retried(
    alice: ApiUser,
    exam: dict[str, Any],
    small_pdf: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = runner.worker_command
    monkeypatch.setattr(
        runner, "worker_command", lambda *_args: [sys.executable, "-c", "import os; os.abort()"]
    )
    upload = upload_pdf(alice, exam["id"], small_pdf).json()
    monkeypatch.setattr(runner, "worker_command", original)

    response = alice.post(f"/api/uploads/{upload['id']}/retry")

    assert response.status_code == 202
    assert alice.get(f"/api/exams/{exam['id']}/uploads").json()[0]["status"] == "processed"


def test_worker_runs_in_a_separate_process(
    alice: ApiUser,
    exam: dict[str, Any],
    small_pdf: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker reports its process id; it must differ from the server's."""
    import os

    marker = tmp_path / "pid.txt"
    original = runner.worker_command

    def command(pdf: Path, out: Path, settings: Settings) -> list[str]:
        real = original(pdf, out, settings)
        script = (
            f"import os, runpy, sys; open({str(marker)!r}, 'w').write(str(os.getpid())); "
            f"sys.argv = {real[2:]!r}; "
            "runpy.run_module('app.pdf.render_worker', run_name='__main__')"
        )
        return [sys.executable, "-c", script]

    monkeypatch.setattr(runner, "worker_command", command)
    upload_pdf(alice, exam["id"], small_pdf)

    assert alice.get(f"/api/exams/{exam['id']}/uploads").json()[0]["status"] == "processed"
    assert int(marker.read_text()) != os.getpid()
