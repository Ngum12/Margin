"""Phase 2 acceptance (brief section 9, plus owner requirements): generate cover sheets, build a
synthetic scanned PDF, upload it, and check where every page went and why."""

from typing import Any

import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Page, PageState, Script, Student
from app.sheets.cover_pdf import SheetInfo, SheetStudent, build_cover_sheets_pdf
from app.sheets.tokens import new_token
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, upload_pdf
from tests.scan_builder import (
    ScanBuilder,
    answer_page,
    damage_qr,
    erase_frame,
    erase_qr,
    render_pdf_pages,
)

CODES = ["AAAAAA", "BBBBBB", "CCCCCC", "DDDDDD", "EEEEEE", "FFFFFF"]


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def setup(alice: ApiUser, world: World, factory: Factory) -> dict[str, Any]:
    for code in CODES:
        factory.student(world.class_a, code)
    exam = make_ready_exam(alice, world.class_a.id, "Chemistry mock")
    other = make_ready_exam(alice, world.class_a.id, "Economics mock")
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    alice.post(f"/api/exams/{other['id']}/cover-sheets")
    covers = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)
    other_covers = render_pdf_pages(alice.get(f"/api/exams/{other['id']}/cover-sheets.pdf").content)
    # Sheets are sorted by student code, so covers[i] belongs to CODES[i].
    return {
        "exam": exam,
        "other": other,
        "covers": dict(zip(CODES, covers, strict=True)),
        "other_covers": dict(zip(CODES, other_covers, strict=True)),
    }


def _placements(db: Session, upload_id: int) -> list[tuple[int, str | None, str | None, bool]]:
    """(source index, student code or None, reason or None, is_cover) for each page."""
    rows = db.execute(
        select(Page, Student.code)
        .outerjoin(Script, Page.script_id == Script.id)
        .outerjoin(Student, Script.student_id == Student.id)
        .where(Page.upload_id == upload_id)
        .order_by(Page.source_page_index)
    )
    return [
        (
            page.source_page_index,
            code,
            page.unassigned_reason.value if page.unassigned_reason else None,
            page.is_cover,
        )
        for page, code in rows
    ]


def test_synthetic_class_scan_is_split_correctly(
    alice: ApiUser, setup: dict[str, Any], db: Session
) -> None:
    c, oc = setup["covers"], setup["other_covers"]
    unknown_cover = render_pdf_pages(
        build_cover_sheets_pdf(
            SheetInfo("X", "C", "C", "F", None), [SheetStudent("ZZZZZZ", new_token())]
        )
    )[0]
    scan = (
        ScanBuilder()
        .add(answer_page(100))  # 0: before any cover
        .add(c["AAAAAA"])  # 1
        .add(answer_page(1))  # 2
        .add(answer_page(2), pdf_rotation=90)  # 3: scanner recorded /Rotate
        .add(c["BBBBBB"], rotate=180)  # 4: cover upside down
        .add(answer_page(3))  # 5
        .add(damage_qr(c["CCCCCC"]))  # 6: damaged QR codes
        .add(answer_page(4))  # 7
        .add(c["DDDDDD"], rotate=90)  # 8: cover sideways
        .add(answer_page(5))  # 9
        .add(oc["EEEEEE"])  # 10: sheet from another exam
        .add(answer_page(6))  # 11
        .add(erase_qr(c["EEEEEE"]))  # 12: QR codes gone, frame left
        .add(answer_page(7))  # 13
        .add(c["FFFFFF"])  # 14
        .add(answer_page(8))  # 15
        .add(c["AAAAAA"])  # 16: duplicated sheet in the same upload
        .add(answer_page(9))  # 17
        .add(unknown_cover)  # 18: well-formed token that is not in this installation
        .add(answer_page(10))  # 19
    ).build()

    upload = upload_pdf(alice, setup["exam"]["id"], scan).json()

    assert alice.get(f"/api/exams/{setup['exam']['id']}/uploads").json()[0]["status"] == "processed"
    follows = "follows_unassigned_cover"
    assert _placements(db, upload["id"]) == [
        (0, None, "before_first_cover", False),
        (1, "AAAAAA", None, True),
        (2, "AAAAAA", None, False),
        (3, "AAAAAA", None, False),
        (4, "BBBBBB", None, True),
        (5, "BBBBBB", None, False),
        (6, None, "qr_damaged", True),
        (7, None, follows, False),
        (8, "DDDDDD", None, True),
        (9, "DDDDDD", None, False),
        (10, None, "other_exam", True),
        (11, None, follows, False),
        (12, None, "qr_unreadable", True),
        (13, None, follows, False),
        (14, "FFFFFF", None, True),
        (15, "FFFFFF", None, False),
        (16, None, "duplicate_in_upload", True),
        (17, None, follows, False),
        (18, None, "unknown_sheet", True),
        (19, None, follows, False),
    ]

    pages = {p.source_page_index: p for p in db.scalars(select(Page))}
    # Images are stored as scanned; rotated covers record the turn that makes them upright and
    # it carries to the answer pages after them (layer b). /Rotate is applied by PDFium.
    assert pages[4].rotation_stack == 180
    assert pages[5].rotation_stack == 180
    assert pages[8].rotation_stack in (90, 270)
    assert pages[9].rotation_stack == pages[8].rotation_stack
    assert pages[8].width > pages[8].height
    assert pages[3].width > pages[3].height
    assert pages[1].rotation_stack == pages[2].rotation_stack == 0
    # The cover with damaged codes resets the stack rotation.
    assert pages[6].rotation_stack == pages[7].rotation_stack == 0
    assert all(p.rotation_baked == 0 for p in pages.values())
    # Follow-on pages point at the problem cover they follow.
    assert pages[7].related_page_id == pages[6].id
    # Script page order is cover first, then answers in scan order.
    script_a = db.scalars(select(Script).join(Student).where(Student.code == "AAAAAA")).one()
    assert [(p.position, p.source_page_index) for p in script_a.pages] == [(1, 1), (2, 2), (3, 3)]


def test_tray_names_the_other_exam_and_scripts_list_missing_students(
    alice: ApiUser, setup: dict[str, Any]
) -> None:
    c, oc = setup["covers"], setup["other_covers"]
    exam_id = setup["exam"]["id"]
    upload_pdf(
        alice, exam_id, ScanBuilder().add(c["AAAAAA"]).add(oc["BBBBBB"]).add(answer_page(1)).build()
    )

    tray = alice.get(f"/api/exams/{exam_id}/unassigned-pages").json()
    scripts = alice.get(f"/api/exams/{exam_id}/scripts").json()

    other = next(p for p in tray if p["unassigned_reason"] == "other_exam")
    assert other["detected_exam_title"] == "Economics mock"
    assert [s["student"]["code"] for s in scripts["scripts"]] == ["AAAAAA"]
    assert [s["code"] for s in scripts["missing"]] == CODES[1:]


def test_sheet_from_an_earlier_upload_is_not_merged(
    alice: ApiUser, setup: dict[str, Any], db: Session
) -> None:
    c = setup["covers"]
    exam_id = setup["exam"]["id"]
    first = upload_pdf(
        alice, exam_id, ScanBuilder().add(c["AAAAAA"]).add(answer_page(1)).build()
    ).json()

    second = upload_pdf(
        alice, exam_id, ScanBuilder().add(c["AAAAAA"]).add(answer_page(2)).add(c["BBBBBB"]).build()
    ).json()

    assert _placements(db, first["id"]) == [(0, "AAAAAA", None, True), (1, "AAAAAA", None, False)]
    assert _placements(db, second["id"]) == [
        (0, None, "already_uploaded", True),
        (1, None, "follows_unassigned_cover", False),
        (2, "BBBBBB", None, True),
    ]


def test_exam_cannot_return_to_draft_after_upload(alice: ApiUser, setup: dict[str, Any]) -> None:
    exam_id = setup["exam"]["id"]
    upload_pdf(alice, exam_id, ScanBuilder().add(setup["covers"]["AAAAAA"]).build())

    response = alice.put(f"/api/exams/{exam_id}/status", json={"status": "draft"})

    assert response.status_code == 409
    assert response.json()["code"] == "exam.has_scripts"
    assert alice.get(f"/api/exams/{exam_id}").json()["status"] == "ready"


def test_exam_summary_counts_scripts(alice: ApiUser, setup: dict[str, Any]) -> None:
    c = setup["covers"]
    upload_pdf(alice, setup["exam"]["id"], ScanBuilder().add(c["AAAAAA"]).add(c["BBBBBB"]).build())

    summary = next(e for e in alice.get("/api/exams").json() if e["id"] == setup["exam"]["id"])

    assert summary["scripts"] == {"waiting": 2, "ai_marked": 0, "confirmed": 0}


def test_processing_is_audited(alice: ApiUser, setup: dict[str, Any], db: Session) -> None:
    upload = upload_pdf(
        alice, setup["exam"]["id"], ScanBuilder().add(setup["covers"]["AAAAAA"]).build()
    )

    actions = [
        e.action
        for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "upload"))
        if e.entity_id == upload.json()["id"]
    ]
    assert actions == ["create", "process"]


def test_upside_down_cover_is_upright_after_its_effective_rotation(
    alice: ApiUser, setup: dict[str, Any], db: Session, settings: Any
) -> None:
    upload_pdf(
        alice, setup["exam"]["id"], ScanBuilder().add(setup["covers"]["AAAAAA"], rotate=180).build()
    )

    page = db.scalars(select(Page)).one()
    assert page.effective_rotation == 180
    # The stored file is unchanged; turning it clockwise by the effective rotation makes it upright.
    image = Image.open(settings.data_dir / page.image_path).rotate(
        -page.effective_rotation, expand=True
    )
    # Upright: the student code block is in the top half (dark pixels concentrated there).
    gray = image.convert("L").resize((50, 70))

    def dark(x: int, y: int) -> bool:
        value = gray.getpixel((x, y))
        return isinstance(value, int) and value < 100

    top = sum(dark(x, y) for y in range(0, 35) for x in range(50))
    bottom = sum(dark(x, y) for y in range(35, 70) for x in range(50))
    assert page.state == PageState.ASSIGNED
    assert top > bottom


def test_cover_with_unreadable_code_is_never_merged_into_previous_script(
    alice: ApiUser, setup: dict[str, Any], db: Session
) -> None:
    """Owner fix 2026-10-14: frame found but code unreadable -> tray, with its following pages."""
    c = setup["covers"]
    scan = (
        ScanBuilder()
        .add(c["AAAAAA"])
        .add(answer_page(1))
        .add(answer_page(2))
        .add(erase_qr(c["BBBBBB"]))
        .add(answer_page(3))
        .add(answer_page(4))
        .add(c["CCCCCC"])
        .add(answer_page(5))
    ).build()

    upload = upload_pdf(alice, setup["exam"]["id"], scan).json()

    placements = _placements(db, upload["id"])
    assert [p[1] for p in placements] == ["AAAAAA"] * 3 + [None] * 3 + ["CCCCCC"] * 2
    assert [p[2] for p in placements[3:6]] == [
        "qr_unreadable",
        "follows_unassigned_cover",
        "follows_unassigned_cover",
    ]
    scripts = alice.get(f"/api/exams/{setup['exam']['id']}/scripts").json()
    pages = {s["student"]["code"]: len(s["pages"]) for s in scripts["scripts"]}
    assert pages == {"AAAAAA": 3, "CCCCCC": 2}


def test_unusual_page_count_is_flagged_when_a_cover_is_completely_unreadable(
    alice: ApiUser, setup: dict[str, Any]
) -> None:
    """Residual risk of D-029: codes and frame both destroyed, so the cover looks like an answer
    page and joins the previous script. The page-count check (D-036) flags it for the teacher."""
    c = setup["covers"]
    builder = ScanBuilder()
    for i, code in enumerate(["AAAAAA", "BBBBBB", "CCCCCC", "DDDDDD"]):
        builder.add(c[code]).add(answer_page(10 * i)).add(answer_page(10 * i + 1))
    # EEEEEE's cover is unrecognisable; its pages will follow DDDDDD's.
    builder.add(erase_frame(erase_qr(c["EEEEEE"]))).add(answer_page(50)).add(answer_page(51))

    upload_pdf(alice, setup["exam"]["id"], builder.build())

    overview = alice.get(f"/api/exams/{setup['exam']['id']}/scripts").json()
    flags = {s["student"]["code"]: s["page_count_flag"] for s in overview["scripts"]}
    assert overview["typical_page_count"] == 3
    assert flags == {"AAAAAA": None, "BBBBBB": None, "CCCCCC": None, "DDDDDD": "more_than_usual"}
    assert "EEEEEE" in [m["code"] for m in overview["missing"]]


def test_script_with_only_a_cover_is_flagged(alice: ApiUser, setup: dict[str, Any]) -> None:
    c = setup["covers"]
    upload_pdf(
        alice,
        setup["exam"]["id"],
        ScanBuilder().add(c["AAAAAA"]).add(c["BBBBBB"]).add(answer_page(1)).build(),
    )

    overview = alice.get(f"/api/exams/{setup['exam']['id']}/scripts").json()

    flags = {s["student"]["code"]: s["page_count_flag"] for s in overview["scripts"]}
    assert flags == {"AAAAAA": "no_answer_pages", "BBBBBB": None}
