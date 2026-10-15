"""Results and exports (Phase 5): results table, CSV, marked PDFs, training dataset, exam
completion, permissions. Nothing unconfirmed is ever exported; names never leave on paper or in
the dataset."""

import csv
import hashlib
import io
import json
import zipfile
from typing import Any

import pypdfium2 as pdfium
import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    Exam,
    ExamStatus,
    Export,
    ExportStatus,
    MarkDecision,
    Page,
    Script,
    Student,
)
from app.exports import fonts
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, start_ai, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page, render_pdf_pages

NAMES = {"AAAAAA": "Ama Fon", "BBBBBB": "Bih Ndi", "CCCCCC": "=HYPERLINK(1)"}


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def bruno(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "bruno")


@pytest.fixture
def admin(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "admin")


def _script_id(db: Session, code: str) -> int:
    found = db.scalar(
        select(Script.id).join(Student, Script.student_id == Student.id).where(Student.code == code)
    )
    assert found is not None
    return found


def _points(alice: ApiUser, script_id: int) -> list[dict[str, Any]]:
    review = alice.get(f"/api/scripts/{script_id}/review").json()
    return [p for q in review["questions"] for p in q["points"]]


@pytest.fixture
def marked(
    app: FastAPI, alice: ApiUser, world: World, factory: Factory, db: Session
) -> dict[str, Any]:
    """Three Mock-marked scripts. AAAAAA (consent) and CCCCCC (no consent) are confirmed;
    BBBBBB (consent) is not. AAAAAA lost a mark on its second point and has a comment."""
    for code, name in NAMES.items():
        student = factory.student(world.class_a, code, name)
        student.training_consent = code != "CCCCCC"
    db.commit()
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    scan = ScanBuilder()
    for i, cover in enumerate(covers):
        scan.add(cover).add(answer_page(i))
    upload_pdf(alice, exam["id"], scan.build())
    start_ai(alice, exam["id"])
    run_jobs(app)

    a, c = _script_id(db, "AAAAAA"), _script_id(db, "CCCCCC")
    second = _points(alice, a)[1]["id"]
    alice.put(f"/api/scripts/{a}/decisions/{second}", json={"marks": 0, "category": "omitted"})
    question = alice.get(f"/api/scripts/{a}/review").json()["questions"][0]["id"]
    alice.put(
        f"/api/scripts/{a}/questions/{question}/comment", json={"text": "Name two properties."}
    )
    for script_id in (a, c):
        alice.post(f"/api/scripts/{script_id}/accept-all")
        assert alice.post(f"/api/scripts/{script_id}/confirm").status_code == 200
    return {"exam_id": exam["id"], "a": a, "b": _script_id(db, "BBBBBB"), "c": c}


def _stored_totals(db: Session, script_id: int) -> dict[str, int]:
    """Per question label: sum of final marks capped at the maximum, straight from the DB."""
    exam = db.scalar(
        select(Exam).join(Script, Script.exam_id == Exam.id).where(Script.id == script_id)
    )
    assert exam is not None
    out = {}
    for question in exam.questions:
        half = sum(
            d.final_half_marks or 0
            for d in db.scalars(
                select(MarkDecision).where(
                    MarkDecision.script_id == script_id,
                    MarkDecision.mark_scheme_point_id.in_([p.id for p in question.points]),
                )
            )
        )
        out[question.label] = min(half, question.max_half_marks) // 2
    return out


# --- results table ----------------------------------------------------------------------------


def test_results_show_confirmed_marks_and_hide_unconfirmed_ones(
    alice: ApiUser, marked: dict[str, Any]
) -> None:
    body = alice.get(f"/api/exams/{marked['exam_id']}/results").json()
    assert [q["label"] for q in body["questions"]] == ["1(a)", "1(b)"]
    rows = {r["student_code"]: r for r in body["rows"]}
    assert rows["AAAAAA"]["marks"] == [1, 1]
    assert (rows["AAAAAA"]["total"], rows["AAAAAA"]["percentage"]) == (2, 66.7)
    assert rows["BBBBBB"] == rows["BBBBBB"] | {
        "confirmed": False,
        "marks": [None, None],
        "total": None,
    }
    assert rows["CCCCCC"]["total"] == 3
    assert (body["confirmed_count"], body["script_count"], body["max_total"]) == (2, 3, 3)
    assert body["average_total"] == 2.5
    assert [q["average"] for q in body["questions"]] == [1.5, 1]
    assert body["timed_count"] == 0


# --- CSV ----------------------------------------------------------------------------------------


def _csv_rows(content: bytes) -> list[list[str]]:
    assert content.startswith(b"\xef\xbb\xbf")  # UTF-8 byte-order mark for spreadsheets
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


def test_csv_totals_match_the_stored_marks_for_confirmed_scripts_only(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    response = alice.get(f"/api/exams/{marked['exam_id']}/results.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    header, *rows = _csv_rows(response.content)

    assert header == [
        "Student code",
        "Name",
        "1(a)",
        "1(b)",
        "Total",
        "Maximum",
        "Percentage",
        "Confirmed at",
        "AI model",
    ]
    assert [r[0] for r in rows] == ["AAAAAA", "CCCCCC"]  # BBBBBB is not confirmed
    for row in rows:
        stored = _stored_totals(db, _script_id(db, row[0]))
        assert [int(row[2]), int(row[3])] == [stored["1(a)"], stored["1(b)"]]
        assert int(row[4]) == sum(stored.values())
        assert row[5] == "3"
    assert rows[1][1] == "'=HYPERLINK(1)"  # never run as a spreadsheet formula
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "export")).one()
    assert event.new_value["kind"] == "csv"
    assert event.new_value["scripts"] == 2


def test_csv_headings_follow_the_teacher_language(alice: ApiUser, marked: dict[str, Any]) -> None:
    alice.put("/api/auth/me/language", json={"preferred_language": "fr"})
    header = _csv_rows(alice.get(f"/api/exams/{marked['exam_id']}/results.csv").content)[0]
    assert header[0] == "Code élève"


# --- marked PDFs ------------------------------------------------------------------------------


def _pdf_text(content: bytes) -> tuple[int, str]:
    pdf = pdfium.PdfDocument(content)
    try:
        text = "".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
        return len(pdf), text
    finally:
        pdf.close()


def test_marked_pdf_needs_a_confirmed_script(alice: ApiUser, marked: dict[str, Any]) -> None:
    response = alice.get(f"/api/scripts/{marked['b']}/marked.pdf")
    assert response.status_code == 409
    assert response.json()["code"] == "export.not_confirmed"


def test_marked_pdf_has_every_page_the_code_the_marks_and_no_name(
    alice: ApiUser, marked: dict[str, Any], db: Session, settings: Any
) -> None:
    pages = db.scalars(select(Page).where(Page.script_id == marked["a"])).all()
    before = {
        p.id: hashlib.sha256((settings.data_dir / p.image_path).read_bytes()).digest()
        for p in pages
    }

    response = alice.get(f"/api/scripts/{marked['a']}/marked.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    count, text = _pdf_text(response.content)
    assert count == len(pages) == 2
    assert "AAAAAA" in text
    assert "Total: 2 / 3" in text
    assert "1(a)" in text
    assert "1 / 2" in text
    # One sign per point, as teachers mark: the first point earned, the second not.
    assert "✓ ✗" in text
    assert b"NotoSans" in response.content
    assert "Name two properties." in text  # the teacher's comment
    assert "Ama Fon" not in text  # codes only on paper
    after = {
        p.id: hashlib.sha256((settings.data_dir / p.image_path).read_bytes()).digest()
        for p in pages
    }
    assert after == before
    assert (
        db.scalars(select(AuditEvent).where(AuditEvent.action == "export")).one().new_value["kind"]
        == "student_pdf"
    )


def test_class_pdf_is_built_in_the_background_with_every_confirmed_script(
    app: FastAPI, alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    response = alice.post(f"/api/exams/{marked['exam_id']}/exports/class-pdf")
    assert response.status_code == 202
    export = response.json()
    assert export["status"] == "pending"
    assert alice.get(f"/api/exports/{export['id']}/file").status_code == 409

    run_jobs(app)

    status = alice.get(f"/api/exports/{export['id']}").json()
    assert status["status"] == "done"
    assert status["size_bytes"] > 0
    file = alice.get(f"/api/exports/{export['id']}/file")
    assert file.status_code == 200
    count, text = _pdf_text(file.content)
    assert count == 4  # AAAAAA and CCCCCC, cover + one answer page each
    assert "AAAAAA" in text
    assert "CCCCCC" in text
    assert "BBBBBB" not in text
    assert not any(name in text for name in NAMES.values())
    listed = alice.get(f"/api/exams/{marked['exam_id']}/results").json()["class_pdfs"]
    assert [e["id"] for e in listed] == [export["id"]]


def test_class_pdf_needs_a_confirmed_script(alice: ApiUser, world: World, factory: Factory) -> None:
    exam = make_ready_exam(alice, world.class_a.id)
    response = alice.post(f"/api/exams/{exam['id']}/exports/class-pdf")
    assert response.status_code == 409
    assert response.json()["code"] == "export.nothing_confirmed"


def test_a_failed_build_is_reported_not_retried(
    app: FastAPI,
    alice: ApiUser,
    marked: dict[str, Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_args: object, **_kwargs: object) -> int:
        raise OSError("disk full")

    monkeypatch.setattr("app.services.exports.write_marked_pdf", broken)
    export = alice.post(f"/api/exams/{marked['exam_id']}/exports/class-pdf").json()
    run_jobs(app)
    status = alice.get(f"/api/exports/{export['id']}").json()
    assert (status["status"], status["error_code"]) == ("failed", "export.failed")


# --- training dataset -------------------------------------------------------------------------


def _dataset(app: FastAPI, admin: ApiUser) -> zipfile.ZipFile:
    response = admin.post("/api/admin/training-export", json={})
    assert response.status_code == 202, response.text
    run_jobs(app)
    export_id = response.json()["id"]
    assert admin.get(f"/api/exports/{export_id}").json()["status"] == "done"
    file = admin.get(f"/api/exports/{export_id}/file")
    assert file.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(file.content))


def test_dataset_holds_only_confirmed_scripts_of_consenting_students(
    app: FastAPI, admin: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    preview = admin.get("/api/admin/training-export").json()
    assert [(e["confirmed"], e["consented"]) for e in preview["exams"]] == [(2, 1)]

    archive = _dataset(app, admin)

    lines = [json.loads(line) for line in archive.read("dataset.jsonl").decode().splitlines()]
    assert [line["student_code"] for line in lines] == ["AAAAAA"]  # not BBBBBB, not CCCCCC
    line = lines[0]
    assert line["exam"]["subject"] == "chemistry"
    assert line["exam"]["curriculum"] == "cm_gce_ol"
    assert line["total"] == 2
    point = line["questions"][0]["points"][1]
    assert (point["final_marks"], point["final_category"]) == (0, "omitted")
    assert point["proposal"]["marks"] == 1  # the model's original proposal kept alongside
    assert point["proposal"]["model"] == "mock-marker"
    assert point["proposal"]["prompt_version"].startswith("marker-lines-v3#")
    answer = line["pages"][1]
    assert answer["transcription"].startswith("1(a)")
    assert answer["reader_prompt_version"].startswith("reader-v2#")
    for page in line["pages"]:
        assert page["image"] in archive.namelist()
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "export")).one()
    assert event.new_value | {"exams": 1, "scripts": 1, "pages": 2} == event.new_value


def test_dataset_contains_no_names_anywhere(
    app: FastAPI, admin: ApiUser, marked: dict[str, Any]
) -> None:
    archive = _dataset(app, admin)
    for member in archive.namelist():
        data = archive.read(member)
        for name in NAMES.values():
            assert name.encode("utf-8") not in data, (member, name)
    # Teacher comments (free text) are not exported either.
    assert b"Name two properties." not in archive.read("dataset.jsonl")


def test_dataset_readme_describes_every_field(
    app: FastAPI, admin: ApiUser, marked: dict[str, Any]
) -> None:
    archive = _dataset(app, admin)
    readme = archive.read("README.md").decode("utf-8")
    line = json.loads(archive.read("dataset.jsonl").decode().splitlines()[0])
    fields = set(line) | set(line["exam"]) | set(line["pages"][0]) | set(line["questions"][0])
    fields |= set(line["questions"][0]["points"][0]) | set(
        line["questions"][0]["points"][0]["proposal"]
    )
    missing = [f for f in fields if f"`{f}`" not in readme]
    assert missing == []


def test_dataset_images_are_upright(
    app: FastAPI, admin: ApiUser, marked: dict[str, Any], db: Session, settings: Any
) -> None:
    page = db.scalars(
        select(Page).where(Page.script_id == marked["a"], Page.is_cover.is_(False))
    ).one()
    page.rotation_teacher = 90
    db.commit()
    with Image.open(settings.data_dir / page.image_path) as image:
        stored = image.size

    archive = _dataset(app, admin)

    exported = Image.open(io.BytesIO(archive.read(f"images/{marked['exam_id']}_AAAAAA_p2.jpg")))
    assert exported.size == (stored[1], stored[0])  # turned a quarter


def test_dataset_is_admin_only(alice: ApiUser, marked: dict[str, Any]) -> None:
    assert alice.post("/api/admin/training-export", json={}).status_code == 403
    assert alice.get("/api/admin/training-export").status_code == 403


def test_dataset_with_no_consented_script_is_refused(
    admin: ApiUser, alice: ApiUser, world: World
) -> None:
    exam = make_ready_exam(alice, world.class_a.id)
    response = admin.post("/api/admin/training-export", json={"exam_ids": [exam["id"]]})
    assert response.status_code == 409
    assert response.json()["code"] == "export.nothing_consented"


def test_teachers_cannot_download_a_dataset(
    app: FastAPI, admin: ApiUser, alice: ApiUser, marked: dict[str, Any]
) -> None:
    export_id = admin.post("/api/admin/training-export", json={}).json()["id"]
    run_jobs(app)
    assert alice.get(f"/api/exports/{export_id}").status_code == 404
    assert alice.get(f"/api/exports/{export_id}/file").status_code == 404


# --- exam completion ----------------------------------------------------------------------------


def test_exam_completes_when_every_script_is_confirmed_and_reopens(
    alice: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    exam_url = f"/api/exams/{marked['exam_id']}"
    assert alice.get(exam_url).json()["status"] == "reviewing"
    alice.post(f"/api/scripts/{marked['b']}/accept-all")
    alice.post(f"/api/scripts/{marked['b']}/confirm")
    assert alice.get(exam_url).json()["status"] == "completed"

    alice.post(f"/api/scripts/{marked['a']}/reopen")
    assert alice.get(exam_url).json()["status"] == "reviewing"
    changes = [
        (e.old_value, e.new_value)
        for e in db.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "exam", AuditEvent.action == "set_status"
            )
        )
        if e.actor_id is not None and e.new_value in ("completed", "reviewing")
    ]
    assert changes[-2:] == [("reviewing", "completed"), ("completed", "reviewing")]
    assert db.get_one(Exam, marked["exam_id"]).status == ExamStatus.REVIEWING


# --- permissions --------------------------------------------------------------------------------


def test_another_teacher_gets_not_found_on_every_results_endpoint(
    app: FastAPI, alice: ApiUser, bruno: ApiUser, marked: dict[str, Any], db: Session
) -> None:
    export_id = alice.post(f"/api/exams/{marked['exam_id']}/exports/class-pdf").json()["id"]
    run_jobs(app)
    responses = [
        bruno.get(f"/api/exams/{marked['exam_id']}/results"),
        bruno.get(f"/api/exams/{marked['exam_id']}/results.csv"),
        bruno.get(f"/api/scripts/{marked['a']}/marked.pdf"),
        bruno.post(f"/api/exams/{marked['exam_id']}/exports/class-pdf"),
        bruno.get(f"/api/exports/{export_id}"),
        bruno.get(f"/api/exports/{export_id}/file"),
    ]
    assert [r.status_code for r in responses] == [404] * len(responses)
    assert (
        db.scalars(
            select(Export).where(
                Export.requested_by_id
                != db.scalar(select(Script.confirmed_by_id).where(Script.id == marked["a"]))
            )
        ).all()
        == []
    )
    assert all(e.status == ExportStatus.DONE for e in db.scalars(select(Export)))


def test_admin_sees_the_model_configuration(admin: ApiUser, alice: ApiUser) -> None:
    body = admin.get("/api/admin/model-config").json()
    assert body["ai_backend"] == "mock"
    assert body["orientation_check"] == "off"
    assert body["model_timeout_seconds"] == 300
    assert alice.get("/api/admin/model-config").status_code == 403


def test_pdf_text_keeps_french_and_ticks_and_leaves_out_what_no_font_has() -> None:
    """Owner, 2026-10-15: ticks print (Noto Sans Symbols 2); emoji are left out, not "?"."""
    assert fonts.printable("Révisez le chapitre 3 ✓ ✗ 😀") == "Révisez le chapitre 3 ✓ ✗ "
    assert fonts.printable("Très bien, élève « à l'écoute »") == "Très bien, élève « à l'écoute »"


def test_bundled_fonts_match_the_approved_files() -> None:
    """The files are exactly the approved releases (checksums in fonts.json)."""
    for family in fonts.manifest():
        assert family["licence"] == "OFL-1.1"
        assert (fonts.FONT_DIR / str(family["licence_file"])).is_file()
        files = family["files"]
        assert isinstance(files, dict)
        for name, digest in files.items():
            assert hashlib.sha256((fonts.FONT_DIR / name).read_bytes()).hexdigest() == digest
    assert ord(fonts.TICK) in fonts._covered(fonts.SYMBOLS)
    assert ord(fonts.CROSS) in fonts._covered(fonts.SYMBOLS)
