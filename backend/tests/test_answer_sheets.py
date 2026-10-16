from pathlib import Path

from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select

from app.config import Settings
from app.db.models import AnswerSheet, IntakePage, Page, Script, Student, UnassignedReason
from app.pdf.render_worker import _read_qr
from app.services import answer_sheets, scan_inbox
from app.services.identification import identify_spare
from app.sheets.tokens import parse_payload
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, upload_pdf
from tests.fake_ollama import FakeOllama
from tests.scan_builder import ScanBuilder, render_pdf_pages


def test_shuffled_numbered_pages_spares_duplicates_and_missing_pages(
    app: FastAPI, world: World, factory: Factory, settings: Settings, tmp_path: Path
) -> None:
    alice = ApiUser(app, "alice")
    first = factory.student(world.class_a, "AAAAAA", "Student Alpha")
    factory.student(world.class_a, "BBBBBB", "Student Beta")
    exam = make_ready_exam(alice, world.class_a.id)
    response = alice.post(
        f"/api/exams/{exam['id']}/answer-sheets",
        json={"pages_per_student": 2, "spares": 1, "request_key": "a" * 24},
    )
    assert response.status_code == 201, response.text
    images = render_pdf_pages(alice.get(response.json()["download_url"]).content)
    assert len(images) == 5
    for image in images:
        texts = _read_qr(image)["texts"]
        assert len(texts) == 1
        assert parse_payload(texts[0]).token
        assert "Student" not in texts[0]

    def ingest(name: str, content: bytes) -> int:
        path = tmp_path / name
        path.write_bytes(content)
        with app.state.sessionmaker() as db:
            batch = scan_inbox.receive(db, world.school.id, path, settings)
            assert batch
            ident = batch.id
            db.commit()
        scan_inbox.process(app.state.sessionmaker, settings, ident)
        return ident

    ingest("first.pdf", ScanBuilder().add(images[1].rotate(180)).build())
    with app.state.sessionmaker() as db:
        assert answer_sheets.readiness(db, exam["id"], first.id) == ([1], False)
    ingest(
        "rest.pdf",
        ScanBuilder()
        .add(images[3].rotate(90, expand=True))
        .add(images[0])
        .add(images[2].rotate(270, expand=True))
        .add(images[1])
        .add(images[4])
        .build(),
    )
    with app.state.sessionmaker() as db:
        script = db.scalar(select(Script).where(Script.student_id == first.id))
        assert script
        assert [p.position for p in script.pages] == [1, 2]
        assert all(not p.is_cover for p in script.pages)
        assert answer_sheets.readiness(db, exam["id"], first.id) == ([], True)
        duplicate = db.scalar(select(IntakePage).where(IntakePage.reason == "duplicate_page"))
        spare = db.scalar(select(IntakePage).where(IntakePage.reason == "spare"))
        assert duplicate
        assert spare
        duplicate_id, spare_id = duplicate.id, spare.id
        page = script.pages[0]
        original = (settings.data_dir / page.image_path).read_bytes()
        masked, rotation = answer_sheets.grading_image(db, page, settings)
        assert rotation == 0
        with Image.open(masked) as image:
            header = image.crop((0, 0, image.width, round(image.height * 42 / 297)))
            assert header.getextrema() == ((255, 255), (255, 255), (255, 255))
            with Image.open(settings.data_dir / page.image_path) as source:
                original_header = source.convert("RGB").crop(
                    (0, 0, source.width, round(source.height * 42 / 297))
                )
                assert original_header.getextrema() != header.getextrema()
        assert (settings.data_dir / page.image_path).read_bytes() == original
    with FakeOllama() as fake:
        fake.default_reply = '{"name": "Student Alpha"}'
        local_settings = settings.model_copy(
            update={"ai_backend": "ollama", "model_base_url": fake.url}
        )
        identify_spare(app.state.sessionmaker, local_settings, {"intake_page_id": spare_id})
        assert len(fake.requests) == 1
    with app.state.sessionmaker() as db:
        suggestion = db.get(IntakePage, spare_id)
        assert suggestion
        assert suggestion.suggested_student_id == first.id
        assert suggestion.page_id is None
        assert suggestion.identification_model
    assert alice.post(f"/api/intake/{duplicate_id}/discard").status_code == 204
    assert (
        alice.post(
            f"/api/intake/{spare_id}/assign",
            json={"exam_id": exam["id"], "student_id": first.id, "page_number": 3},
        ).status_code
        == 204
    )
    with app.state.sessionmaker() as db:
        assert answer_sheets.readiness(db, exam["id"], first.id) == ([], False)
        assert len(list(db.scalars(select(Page)))) == 5


def test_manual_upload_routes_answer_sheets_without_cover_order(
    app: FastAPI, world: World, factory: Factory
) -> None:
    alice = ApiUser(app, "alice")
    student = factory.student(world.class_a, "AAAAAA")
    exam = make_ready_exam(alice, world.class_a.id)
    prepared = alice.post(
        f"/api/exams/{exam['id']}/answer-sheets",
        json={"pages_per_student": 2, "spares": 1, "request_key": "b" * 24},
    ).json()
    images = render_pdf_pages(alice.get(prepared["download_url"]).content)
    response = upload_pdf(
        alice, exam["id"], ScanBuilder().add(images[1]).add(images[0]).add(images[2]).build()
    )
    assert response.status_code == 202
    with app.state.sessionmaker() as db:
        script = db.scalar(select(Script).where(Script.student_id == student.id))
        assert script
        assert [p.position for p in script.pages] == [1, 2]
        spare = db.scalar(
            select(Page).where(Page.unassigned_reason == UnassignedReason.SPARE_SHEET)
        )
        assert spare
        assert spare.answer_sheet_id


def test_sheet_permission_and_label_stock(app: FastAPI, world: World, factory: Factory) -> None:
    alice, bruno = ApiUser(app, "alice"), ApiUser(app, "bruno")
    factory.student(world.class_a, "AAAAAA", "Private Name")
    exam = make_ready_exam(alice, world.class_a.id)
    body = {"pages_per_student": 1, "spares": 0, "layout": "labels", "request_key": "c" * 24}
    assert bruno.post(f"/api/exams/{exam['id']}/answer-sheets", json=body).status_code == 404
    prepared = alice.post(f"/api/exams/{exam['id']}/answer-sheets", json=body).json()
    assert (
        alice.post(f"/api/exams/{exam['id']}/answer-sheets", json=body).json()["id"]
        == prepared["id"]
    )
    assert bruno.get(prepared["download_url"]).status_code == 404
    images = render_pdf_pages(alice.get(prepared["download_url"]).content)
    assert len(images) == 1
    assert len(_read_qr(images[0])["texts"]) == 1
    with app.state.sessionmaker() as db:
        sheet = db.scalar(select(AnswerSheet))
        assert sheet
        assert sheet.layout == "labels"
        assert db.scalar(select(Student.display_name)) == "Private Name"


def test_automatic_start_waits_for_every_numbered_page(
    app: FastAPI, world: World, factory: Factory, settings: Settings, tmp_path: Path
) -> None:
    from app.db.models import Job, ScriptStatus
    from app.services.automatic_marking import tick
    from tests.factories import run_jobs

    alice = ApiUser(app, "alice")
    factory.student(world.class_a, "CCCCCC")
    exam = make_ready_exam(alice, world.class_a.id)
    sheets = alice.post(
        f"/api/exams/{exam['id']}/answer-sheets",
        json={"pages_per_student": 2, "spares": 0, "request_key": "auto" * 8},
    ).json()
    images = render_pdf_pages(alice.get(sheets["download_url"]).content)

    def ingest(index: int) -> None:
        path = tmp_path / f"auto{index}.pdf"
        path.write_bytes(ScanBuilder().add(images[index]).build())
        with app.state.sessionmaker() as db:
            batch = scan_inbox.receive(db, world.school.id, path, settings)
            assert batch
            batch_id = batch.id
            db.commit()
        scan_inbox.process(app.state.sessionmaker, settings, batch_id)

    ingest(0)
    assert tick(app.state.sessionmaker, settings) == 0
    ingest(1)
    assert tick(app.state.sessionmaker, settings) == 1
    assert tick(app.state.sessionmaker, settings) == 0
    with app.state.sessionmaker() as db:
        assert len(list(db.scalars(select(Job)))) == 1
    run_jobs(app)
    with app.state.sessionmaker() as db:
        assert db.scalars(select(Script)).one().status == ScriptStatus.AI_MARKED
    assert (
        alice.get(f"/api/exams/{exam['id']}/queue").json()["items"][0]["lifecycle"]
        == "ready_for_review"
    )
    bruno = ApiUser(app, "bruno")
    assert (
        bruno.put(f"/api/exams/{exam['id']}/automatic-marking", json={"enabled": False}).status_code
        == 404
    )
    assert (
        alice.put(f"/api/exams/{exam['id']}/automatic-marking", json={"enabled": False}).json()[
            "auto_start_marking"
        ]
        is False
    )
