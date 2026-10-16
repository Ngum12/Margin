import io
from pathlib import Path

from fastapi import FastAPI
from PIL import Image, ImageDraw
from sqlalchemy import select

from app.config import Settings
from app.db.models import IntakePage, ScanBatch, Script
from app.pdf.capture_worker import prepare as prepare_image
from app.services import answer_sheets, capture, scan_inbox
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam
from tests.scan_builder import render_pdf_pages


def jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95)
    return out.getvalue()


def test_photo_preview_precedes_routing_and_keeps_original(
    app: FastAPI, world: World, factory: Factory, settings: Settings
) -> None:
    alice, bruno = ApiUser(app, "alice"), ApiUser(app, "bruno")
    student = factory.student(world.class_a, "AAAAAA", "Local Name")
    exam = make_ready_exam(alice, world.class_a.id)
    sheets = alice.post(
        f"/api/exams/{exam['id']}/answer-sheets",
        json={"pages_per_student": 1, "spares": 0, "request_key": "photo" * 8},
    ).json()
    page = render_pdf_pages(alice.get(sheets["download_url"]).content)[0]
    photo = Image.new("RGB", (page.width + 160, page.height + 160), (40, 40, 40))
    photo.paste(page, (80, 80))
    original = jpeg(photo.rotate(-3, expand=True, fillcolor=(40, 40, 40)))
    result = alice.post("/api/capture?suffix=.jpg", content=original)
    assert result.status_code == 202, result.text
    batch_id = result.json()["id"]
    assert alice.post("/api/capture?suffix=.jpg", content=original).json()["id"] == batch_id
    assert alice.client.post("/api/capture?suffix=.jpg", content=original).status_code == 403
    assert bruno.get(f"/api/capture/{batch_id}/image").status_code == 404
    assert alice.post(f"/api/capture/{batch_id}/accept").status_code == 409
    capture.prepare(app.state.sessionmaker, settings)
    with app.state.sessionmaker() as db:
        batch = db.get_one(ScanBatch, batch_id)
        assert batch.status == "capture_preview"
        assert (settings.data_dir / batch.stored_path).read_bytes() == original
        assert db.scalars(select(Script)).all() == []
    assert alice.get(f"/api/capture/{batch_id}/image").status_code == 200
    assert (
        alice.get(f"/api/capture/{batch_id}/image?original=true").headers["content-type"]
        == "image/png"
    )
    assert (
        alice.put(f"/api/capture/{batch_id}/options", json={"left": 0.9, "right": 0.1}).status_code
        == 422
    )
    assert alice.post(f"/api/capture/{batch_id}/accept").status_code == 200
    scan_inbox.process(app.state.sessionmaker, settings, batch_id)
    with app.state.sessionmaker() as db:
        script = db.scalars(select(Script)).one()
        assert script.student_id == student.id
        assert len(script.pages) == 1
        assert answer_sheets.readiness(db, exam["id"], student.id) == ([], False)
        assert (
            settings.data_dir / db.get_one(ScanBatch, batch_id).stored_path
        ).read_bytes() == original
    assert alice.put(f"/api/capture/{batch_id}/options", json={}).status_code == 409


def test_unknown_phone_page_is_private_and_can_match_an_expected_number(
    app: FastAPI, world: World, factory: Factory, settings: Settings
) -> None:
    alice, bruno = ApiUser(app, "alice"), ApiUser(app, "bruno")
    student = factory.student(world.class_a, "BBBBBB")
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(
        f"/api/exams/{exam['id']}/answer-sheets",
        json={"pages_per_student": 2, "spares": 0, "request_key": "unknown" * 5},
    )
    photo = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(photo).text((40, 100), "Answer without a readable QR", fill="black")
    batch_id = alice.post("/api/capture?suffix=.jpg", content=jpeg(photo)).json()["id"]
    capture.prepare(app.state.sessionmaker, settings)
    alice.post(f"/api/capture/{batch_id}/accept")
    scan_inbox.process(app.state.sessionmaker, settings, batch_id)
    with app.state.sessionmaker() as db:
        item = db.scalars(select(IntakePage).where(IntakePage.batch_id == batch_id)).one()
        item_id = item.id
    assert len(alice.get("/api/intake").json()["pages"]) == 1
    assert bruno.get("/api/intake").json()["pages"] == []
    assert bruno.get(f"/api/intake/{item_id}/image").status_code == 404
    assert alice.get(f"/api/intake/{item_id}/image").status_code == 200
    assigned = alice.post(
        f"/api/intake/{item_id}/assign",
        json={"exam_id": exam["id"], "student_id": student.id, "page_number": 2},
    )
    assert assigned.status_code == 204, assigned.text
    with app.state.sessionmaker() as db:
        assert answer_sheets.readiness(db, exam["id"], student.id) == ([1], False)
        script = db.scalars(select(Script)).one()
        assert script.pages[0].position == 2


def test_crop_uses_original_coordinates_and_retains_colour(tmp_path: Path) -> None:
    source = tmp_path / "original.png"
    target = tmp_path / "prepared.png"
    photo = Image.new("RGB", (1000, 800), (20, 20, 20))
    ImageDraw.Draw(photo).rectangle((250, 200, 750, 600), fill=(250, 30, 40))
    photo.save(source)
    original = source.read_bytes()
    prepare_image(
        source,
        target,
        {
            "left": 0.25,
            "top": 0.25,
            "right": 0.75,
            "bottom": 0.75,
            "auto_crop": True,
            "auto_straighten": False,
            "clean": False,
        },
    )
    with Image.open(target) as result:
        assert result.size == (500, 400)
        assert result.getpixel((250, 200)) == (250, 30, 40)
    assert source.read_bytes() == original


def test_unreadable_capture_is_quarantined(app: FastAPI, world: World, settings: Settings) -> None:
    alice = ApiUser(app, "alice")
    batch_id = alice.post("/api/capture?suffix=.jpg", content=b"not an image").json()["id"]
    capture.prepare(app.state.sessionmaker, settings)
    row = alice.get("/api/capture").json()[0]
    assert row["status"] == "quarantine"
    assert row["error_code"] == "capture.image_unreadable"
    assert alice.post(f"/api/capture/{batch_id}/accept").status_code == 409
