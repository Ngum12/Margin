import struct
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import func, select

from app.clock import utcnow
from app.config import Settings
from app.db.models import (
    IntakePage,
    MarkDecision,
    Page,
    PrintJob,
    Question,
    ScanBatch,
    Script,
    ScriptStatus,
)
from app.services import ipp, printing, scan_inbox
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages


@pytest.mark.parametrize(
    "uri",
    [
        "ipp://8.8.8.8/print",
        "http://192.168.1.2/",
        "ipp://printer.example/",
        "ipp://169.254.169.254/",
        "ipp://user:pass@192.168.1.2/",
        "ipp://[::1]/",
    ],
)
def test_printer_address_rejects_external_and_ambiguous_targets(uri: str) -> None:
    with pytest.raises(ipp.PrinterError):
        ipp.validate_uri(uri)


def test_ipp_response_checks_status_lengths_and_repeated_values() -> None:
    header = struct.pack(">BBHI", 1, 1, 0, 1)
    response = (
        header
        + b"\x04"
        + ipp.attribute(0x21, "job-id", 42)
        + ipp.attribute(0x49, "document-format-supported", "application/pdf")
        + ipp.attribute(0x49, "", "image/jpeg")
        + b"\x03"
    )
    assert ipp.parse_response(response) == {
        "job-id": [42],
        "document-format-supported": ["application/pdf", "image/jpeg"],
    }
    for invalid in [response[:-2], b"short", struct.pack(">BBHI", 1, 1, 0x0400, 1) + b"\x03"]:
        with pytest.raises(ipp.PrinterError):
            ipp.parse_response(invalid)


def test_inbox_waits_routes_mixed_exams_and_deduplicates(
    app: FastAPI, world: World, factory: Factory, settings: Settings
) -> None:
    alice, bruno, admin = ApiUser(app, "alice"), ApiUser(app, "bruno"), ApiUser(app, "admin")
    factory.student(world.class_a, "AAAAAA")
    factory.student(world.class_b, "BBBBBB")
    exams = [make_ready_exam(alice, world.class_a.id), make_ready_exam(bruno, world.class_b.id)]
    scan = ScanBuilder()
    for user, exam in zip([alice, bruno], exams, strict=True):
        user.post(f"/api/exams/{exam['id']}/cover-sheets")
        cover = render_pdf_pages(user.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)[0]
        scan.add(cover).add(answer_page(1))
    assert (
        admin.put(
            "/api/hardware", json={"inbox_enabled": True, "printer_uri": "", "duplex": True}
        ).status_code
        == 200
    )
    folder = scan_inbox.inbox_path(settings, world.school.id)
    source = folder / "copier.pdf"
    content = scan.build()
    source.write_bytes(content)
    poller = scan_inbox.InboxPoller(stable_seconds=0)
    poller.tick(app.state.sessionmaker, settings)
    with app.state.sessionmaker() as db:
        assert db.scalar(select(func.count()).select_from(ScanBatch)) == 0
    poller.tick(app.state.sessionmaker, settings)
    with app.state.sessionmaker() as db:
        assert db.scalar(select(func.count()).select_from(Script)) == 2
        assert db.scalar(select(func.count()).select_from(Page)) == 4
        batch = db.scalar(select(ScanBatch))
        assert batch
        assert (settings.data_dir / batch.stored_path).read_bytes() == content
    source.write_bytes(content)
    poller.tick(app.state.sessionmaker, settings)
    poller.tick(app.state.sessionmaker, settings)
    with app.state.sessionmaker() as db:
        assert db.scalar(select(func.count()).select_from(ScanBatch)) == 1
        assert db.scalar(select(func.count()).select_from(Page)) == 4
    assert not source.exists()
    with app.state.sessionmaker() as db:
        script = db.scalar(select(Script))
        batch = db.scalar(select(ScanBatch))
        assert script
        assert batch
        batch_id = batch.id
        script_id = script.id
        script.status = ScriptStatus.CONFIRMED
        db.commit()
    assert admin.delete(f"/api/scan-batches/{batch_id}").status_code == 409
    with app.state.sessionmaker() as db:
        script = db.get(Script, script_id)
        assert script
        script.status = ScriptStatus.WAITING
        db.commit()
    assert admin.delete(f"/api/scan-batches/{batch_id}").status_code == 204
    with app.state.sessionmaker() as db:
        assert db.scalar(select(func.count()).select_from(Script)) == 0
        batch = db.get(ScanBatch, batch_id)
        assert batch
        assert (settings.data_dir / batch.stored_path).read_bytes() == content


def test_image_intake_requires_admin_to_match_unknown_pages(
    app: FastAPI, world: World, factory: Factory, settings: Settings, tmp_path: Path
) -> None:
    admin, alice, bruno = ApiUser(app, "admin"), ApiUser(app, "alice"), ApiUser(app, "bruno")
    student = factory.student(world.class_a, "AAAAAA")
    exam = make_ready_exam(alice, world.class_a.id)
    source = tmp_path / "phone.tiff"
    Image.new("RGB", (300, 500), "white").save(
        source, save_all=True, append_images=[Image.new("RGB", (300, 500), "blue")]
    )
    with app.state.sessionmaker() as db:
        batch = scan_inbox.receive(db, world.school.id, source, settings)
        assert batch
        batch_id = batch.id
        db.commit()
    scan_inbox.process(app.state.sessionmaker, settings, batch_id)
    pages = admin.get("/api/intake").json()["pages"]
    assert len(pages) == 2
    assert alice.get("/api/intake").json()["pages"] == []
    assert alice.get(f"/api/intake/{pages[0]['id']}/image").status_code == 404
    assert (
        admin.post(
            f"/api/intake/{pages[0]['id']}/assign",
            json={"exam_id": exam["id"], "student_id": student.id},
        ).status_code
        == 204
    )
    assert bruno.get(f"/api/intake/{pages[0]['id']}/image").status_code == 404
    assert alice.get(f"/api/intake/{pages[0]['id']}/image").status_code == 200
    with app.state.sessionmaker() as db:
        assert db.scalar(select(func.count()).select_from(IntakePage)) == 2


def test_print_queue_deduplicates_and_waits_for_hardware_completion(
    app: FastAPI, world: World, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = ApiUser(app, "admin")
    admin.put(
        "/api/hardware",
        json={
            "inbox_enabled": False,
            "printer_uri": "ipp://192.168.1.20/ipp/print",
            "duplex": True,
        },
    )
    body = {"kind": "test", "request_key": "a" * 20}
    first = admin.post("/api/print-jobs", json=body)
    assert first.status_code == 201
    assert admin.post("/api/print-jobs", json=body).json()["id"] == first.json()["id"]
    calls: list[bytes] = []
    monkeypatch.setattr(ipp, "capabilities", lambda uri: {})

    def submit(uri: str, data: bytes, name: str, duplex: bool) -> int:
        calls.append(data)
        return 123

    monkeypatch.setattr(ipp, "submit", submit)
    monkeypatch.setattr(ipp, "job_state", lambda uri, job_id: 5)
    printing.tick(app.state.sessionmaker, settings)
    assert admin.get("/api/print-jobs").json()[0]["status"] == "sent"
    printing.tick(app.state.sessionmaker, settings)
    assert len(calls) == 1
    assert calls[0].startswith(b"%PDF")
    monkeypatch.setattr(ipp, "job_state", lambda uri, job_id: 9)
    printing.tick(app.state.sessionmaker, settings)
    assert admin.get("/api/print-jobs").json()[0]["status"] == "printed"
    assert ApiUser(app, "alice").get("/api/print-jobs").json() == []


def test_interrupted_submission_is_not_automatically_reprinted(
    app: FastAPI, world: World, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = ApiUser(app, "admin")
    admin.put(
        "/api/hardware",
        json={"inbox_enabled": False, "printer_uri": "ipp://192.168.1.20/ipp/print"},
    )
    job_id = admin.post("/api/print-jobs", json={"kind": "test", "request_key": "b" * 20}).json()[
        "id"
    ]
    with app.state.sessionmaker() as db:
        job = db.get(PrintJob, job_id)
        assert job
        job.status, job.updated_at = "submitting", utcnow() - timedelta(minutes=3)
        db.commit()

    def forbidden(*args: object) -> None:
        pytest.fail("An uncertain print must never be automatically submitted again")

    monkeypatch.setattr(ipp, "submit", forbidden)
    printing.tick(app.state.sessionmaker, settings)
    assert admin.get("/api/print-jobs").json()[0]["status"] == "unknown"
    assert admin.post(f"/api/print-jobs/{job_id}/retry", json={}).status_code == 409
    assert (
        admin.post(
            f"/api/print-jobs/{job_id}/retry", json={"acknowledge_uncertain": True}
        ).status_code
        == 200
    )


def test_hardware_settings_require_admin_and_csrf(app: FastAPI, world: World) -> None:
    alice, admin = ApiUser(app, "alice"), ApiUser(app, "admin")
    assert alice.get("/api/hardware").status_code == 403
    assert (
        admin.client.put(
            "/api/hardware", json={"inbox_enabled": True, "printer_uri": ""}
        ).status_code
        == 403
    )
    assert (
        admin.put(
            "/api/hardware", json={"inbox_enabled": True, "printer_uri": "ipp://8.8.8.8/"}
        ).status_code
        == 422
    )


def test_absence_is_not_a_zero_and_is_scoped(app: FastAPI, world: World, factory: Factory) -> None:
    alice, bruno = ApiUser(app, "alice"), ApiUser(app, "bruno")
    student = factory.student(world.class_a, "AAAAAA")
    exam = make_ready_exam(alice, world.class_a.id)
    url = f"/api/exams/{exam['id']}/attendance/{student.id}"
    assert bruno.put(url, json={"absent": True}).status_code == 404
    assert alice.put(url, json={"absent": True}).status_code == 204
    assert alice.get(f"/api/exams/{exam['id']}/attendance").json()[0]["absent"] is True
    assert alice.get(f"/api/exams/{exam['id']}/scripts").json()["missing"] == []
    with app.state.sessionmaker() as db:
        assert db.scalar(select(func.count()).select_from(Script)) == 0
    assert alice.put(url, json={"absent": False}).status_code == 204
    assert len(alice.get(f"/api/exams/{exam['id']}/scripts").json()["missing"]) == 1


def test_feedback_and_print_version_guards(
    app: FastAPI, world: World, factory: Factory, settings: Settings
) -> None:
    alice, bruno, admin = ApiUser(app, "alice"), ApiUser(app, "bruno"), ApiUser(app, "admin")
    student = factory.student(world.class_a, "AAAAAA", "Test student")
    exam = make_ready_exam(alice, world.class_a.id)
    with app.state.sessionmaker() as db:
        script = Script(exam_id=exam["id"], student_id=student.id)
        db.add(script)
        db.flush()
        script_id = script.id
        for question in db.scalars(select(Question).where(Question.exam_id == exam["id"])):
            for point in question.points:
                db.add(
                    MarkDecision(
                        script_id=script.id,
                        mark_scheme_point_id=point.id,
                        final_half_marks=point.half_marks,
                    )
                )
        db.commit()
    assert alice.get(f"/api/scripts/{script_id}/feedback.pdf").status_code == 409
    with app.state.sessionmaker() as db:
        script = db.get(Script, script_id)
        assert script
        script.status, script.confirmed_at, script.confirmed_by_id = (
            ScriptStatus.CONFIRMED,
            utcnow(),
            world.teacher_a.id,
        )
        db.commit()
    response = alice.get(f"/api/scripts/{script_id}/feedback.pdf")
    assert response.status_code == 200
    assert len(render_pdf_pages(response.content)) == 1
    assert bruno.get(f"/api/scripts/{script_id}/feedback.pdf").status_code == 404
    admin.put(
        "/api/hardware",
        json={"inbox_enabled": False, "printer_uri": "ipp://192.168.1.20/ipp/print"},
    )
    body = {"exam_id": exam["id"], "request_key": "c" * 20, "script_ids": [script_id]}
    job_id = alice.post("/api/print-jobs", json=body).json()["id"]
    assert bruno.post("/api/print-jobs", json={**body, "request_key": "d" * 20}).status_code == 404
    assert (
        alice.post(
            "/api/print-jobs", json={**body, "request_key": "e" * 20, "kind": "test"}
        ).status_code
        == 409
    )
    with app.state.sessionmaker() as db:
        script = db.get(Script, script_id)
        job = db.get(PrintJob, job_id)
        assert script
        assert job
        assert job.duplex is False
        assert printing.build_document(db, job, settings).startswith(b"%PDF")
        script.confirmed_at = utcnow() + timedelta(seconds=1)
        from app.errors import ConflictError

        with pytest.raises(ConflictError, match="Marks changed"):
            printing.build_document(db, job, settings)
