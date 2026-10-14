from typing import Any

import pypdfium2 as pdfium
import pytest
import zxingcpp
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CoverSheet
from app.sheets.tokens import parse_payload
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam
from tests.scan_builder import render_pdf_pages


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def exam(alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    factory.student(world.class_a, "BBBBBB", "Bih Nkeng")
    factory.student(world.class_a, "AAAAAA", "Ama Fon")
    return make_ready_exam(alice, world.class_a.id)


def test_prepare_creates_one_sheet_per_student(alice: ApiUser, exam: dict[str, Any]) -> None:
    before = alice.get(f"/api/exams/{exam['id']}/cover-sheets").json()
    after = alice.post(f"/api/exams/{exam['id']}/cover-sheets").json()

    assert [r["has_sheet"] for r in before] == [False, False]
    assert [(r["code"], r["has_sheet"]) for r in after] == [("AAAAAA", True), ("BBBBBB", True)]


def test_tokens_are_stable_and_new_students_get_sheets(
    alice: ApiUser, exam: dict[str, Any], db: Session, factory: Factory, world: World
) -> None:
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    first = {s.student_id: s.token for s in db.scalars(select(CoverSheet))}
    factory.student(world.class_a, "CCCCCC")

    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    db.expire_all()
    second = {s.student_id: s.token for s in db.scalars(select(CoverSheet))}

    assert len(second) == 3
    assert all(second[k] == v for k, v in first.items())


def test_pdf_has_one_page_per_student_and_qr_decodes_to_tokens(
    alice: ApiUser, exam: dict[str, Any], db: Session
) -> None:
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    response = alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    tokens = {s.token for s in db.scalars(select(CoverSheet))}
    decoded = set()
    for image in render_pdf_pages(response.content):
        results = zxingcpp.read_barcodes(image)
        texts = {r.text for r in results if r.valid}
        assert len(texts) == 1  # both codes on a sheet carry the same payload
        parsed = parse_payload(texts.pop())
        decoded.add(parsed.token)
    assert decoded == tokens


def test_pdf_contains_codes_but_no_real_names(alice: ApiUser, exam: dict[str, Any]) -> None:
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    pdf = pdfium.PdfDocument(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    text = " ".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
    pdf.close()

    assert "AAAAAA" in text
    assert "BBBBBB" in text
    assert "Ama" not in text
    assert "Nkeng" not in text
    assert "Mock exam 1" in text


def test_qr_codes_do_not_contain_database_ids(
    alice: ApiUser, exam: dict[str, Any], db: Session
) -> None:
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    pdf = alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content
    texts = {r.text for img in render_pdf_pages(pdf) for r in zxingcpp.read_barcodes(img)}

    for text in texts:
        assert text.startswith("MA1-")
        assert str(exam["id"]) not in text.split("-")


def test_draft_exam_cannot_have_cover_sheets(alice: ApiUser, world: World) -> None:
    exam = alice.post(
        "/api/exams", json={"class_id": world.class_a.id, "subject_code": "chemistry", "title": "D"}
    ).json()

    response = alice.post(f"/api/exams/{exam['id']}/cover-sheets")

    assert response.status_code == 409
    assert response.json()["code"] == "exam.sheets_need_ready"


def test_other_teacher_cannot_get_cover_sheets(
    app: FastAPI, exam: dict[str, Any], world: World
) -> None:
    bruno = ApiUser(app, "bruno")

    assert bruno.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").status_code == 404
    assert bruno.post(f"/api/exams/{exam['id']}/cover-sheets").status_code == 404
