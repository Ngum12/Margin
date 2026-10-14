"""The unassigned tray (assign, return, discard) and resuming interrupted uploads."""

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AuditEvent, Page, PageState, Script, Upload, UploadStatus
from app.services.upload_processor import UploadProcessor
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, upload_pdf
from tests.scan_builder import ScanBuilder, answer_page, erase_qr, render_pdf_pages


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def setup(alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    students = [factory.student(world.class_a, code) for code in ("AAAAAA", "BBBBBB")]
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    return {"exam": exam, "covers": covers, "students": students}


def _tray(alice: ApiUser, exam_id: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = alice.get(f"/api/exams/{exam_id}/unassigned-pages").json()
    return result


def test_teacher_assigns_tray_pages_to_a_student(
    alice: ApiUser, setup: dict[str, Any], db: Session
) -> None:
    exam_id = setup["exam"]["id"]
    scan = ScanBuilder().add(erase_qr(setup["covers"][1])).add(answer_page(1)).add(answer_page(2))
    upload_pdf(alice, exam_id, scan.build())
    tray = _tray(alice, exam_id)
    assert [p["unassigned_reason"] for p in tray] == [
        "qr_unreadable",
        "follows_unassigned_cover",
        "follows_unassigned_cover",
    ]

    response = alice.post(
        f"/api/exams/{exam_id}/pages/assign",
        json={"page_ids": [p["id"] for p in tray], "student_id": setup["students"][1].id},
    )

    assert response.status_code == 204
    assert _tray(alice, exam_id) == []
    script = alice.get(f"/api/exams/{exam_id}/scripts").json()["scripts"][0]
    assert script["student"]["code"] == "BBBBBB"
    assert [p["position"] for p in script["pages"]] == [1, 2, 3]
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "assign_pages")).one()
    assert event.new_value["student_code"] == "BBBBBB"


def test_returning_a_page_to_the_tray_renumbers_the_script(
    alice: ApiUser, setup: dict[str, Any]
) -> None:
    exam_id = setup["exam"]["id"]
    upload_pdf(
        alice,
        exam_id,
        ScanBuilder().add(setup["covers"][0]).add(answer_page(1)).add(answer_page(2)).build(),
    )
    script = alice.get(f"/api/exams/{exam_id}/scripts").json()["scripts"][0]
    middle = script["pages"][1]["id"]

    alice.post(f"/api/exams/{exam_id}/pages/unassign", json={"page_ids": [middle]})

    script = alice.get(f"/api/exams/{exam_id}/scripts").json()["scripts"][0]
    assert [p["position"] for p in script["pages"]] == [1, 2]
    tray = _tray(alice, exam_id)
    assert [(p["id"], p["unassigned_reason"]) for p in tray] == [(middle, "returned_by_teacher")]


def test_returning_every_page_removes_the_script(alice: ApiUser, setup: dict[str, Any]) -> None:
    exam_id = setup["exam"]["id"]
    upload_pdf(alice, exam_id, ScanBuilder().add(setup["covers"][0]).build())
    page_id = alice.get(f"/api/exams/{exam_id}/scripts").json()["scripts"][0]["pages"][0]["id"]

    alice.post(f"/api/exams/{exam_id}/pages/unassign", json={"page_ids": [page_id]})

    scripts = alice.get(f"/api/exams/{exam_id}/scripts").json()
    assert scripts["scripts"] == []
    assert len(scripts["missing"]) == 2


def test_discard_and_restore(alice: ApiUser, setup: dict[str, Any]) -> None:
    exam_id = setup["exam"]["id"]
    upload_pdf(alice, exam_id, ScanBuilder().add(answer_page(1)).add(setup["covers"][0]).build())
    blank = _tray(alice, exam_id)[0]

    alice.post(f"/api/exams/{exam_id}/pages/discard", json={"page_ids": [blank["id"]]})
    assert _tray(alice, exam_id)[0]["state"] == "discarded"

    alice.post(f"/api/exams/{exam_id}/pages/unassign", json={"page_ids": [blank["id"]]})
    restored = _tray(alice, exam_id)[0]
    assert restored["state"] == "unassigned"
    assert restored["unassigned_reason"] == "before_first_cover"


def test_assigned_pages_cannot_be_discarded_or_assigned_again(
    alice: ApiUser, setup: dict[str, Any]
) -> None:
    exam_id = setup["exam"]["id"]
    upload_pdf(alice, exam_id, ScanBuilder().add(setup["covers"][0]).build())
    page_id = alice.get(f"/api/exams/{exam_id}/scripts").json()["scripts"][0]["pages"][0]["id"]

    discard = alice.post(f"/api/exams/{exam_id}/pages/discard", json={"page_ids": [page_id]})
    assign = alice.post(
        f"/api/exams/{exam_id}/pages/assign",
        json={"page_ids": [page_id], "student_id": setup["students"][1].id},
    )

    assert discard.json()["code"] == assign.json()["code"] == "page.already_assigned"


def test_tray_actions_are_scoped_to_the_exam_and_class(
    app: FastAPI, alice: ApiUser, setup: dict[str, Any], world: World, factory: Factory
) -> None:
    exam_id = setup["exam"]["id"]
    upload_pdf(alice, exam_id, ScanBuilder().add(answer_page(1)).build())
    page_id = _tray(alice, exam_id)[0]["id"]
    outsider = factory.student(world.class_b, "XXXXXX")
    other_exam = make_ready_exam(alice, world.class_a.id, "Other")

    wrong_class = alice.post(
        f"/api/exams/{exam_id}/pages/assign",
        json={"page_ids": [page_id], "student_id": outsider.id},
    )
    wrong_exam = alice.post(
        f"/api/exams/{other_exam['id']}/pages/discard", json={"page_ids": [page_id]}
    )
    bruno = ApiUser(app, "bruno").post(
        f"/api/exams/{exam_id}/pages/discard", json={"page_ids": [page_id]}
    )

    assert wrong_class.status_code == wrong_exam.status_code == bruno.status_code == 404
    assert _tray(alice, exam_id)[0]["state"] == "unassigned"


def test_interrupted_upload_is_resumed_without_duplicates(
    app: FastAPI, alice: ApiUser, setup: dict[str, Any], db: Session, settings: Settings
) -> None:
    exam_id = setup["exam"]["id"]
    upload = upload_pdf(
        alice, exam_id, ScanBuilder().add(setup["covers"][0]).add(answer_page(1)).build()
    ).json()
    # Simulate a power cut after processing had started: status is still "processing".
    row = db.get(Upload, upload["id"])
    assert row is not None
    row.status = UploadStatus.PROCESSING
    db.commit()

    UploadProcessor(app.state.sessionmaker, settings, inline=True).recover()

    db.expire_all()
    assert db.get(Upload, upload["id"]).status == UploadStatus.PROCESSED  # type: ignore[union-attr]
    pages = db.scalars(select(Page).where(Page.upload_id == upload["id"])).all()
    assert len(pages) == 2
    assert all(p.state == PageState.ASSIGNED for p in pages)
    assert len(db.scalars(select(Script)).all()) == 1
    assert [p.position for p in db.scalars(select(Script)).one().pages] == [1, 2]
