"""The red pen (owner, 2026-10-15): lines of writing found on the page, matched to the
transcription, and marks placed beside the answers; on screen and in marked PDFs."""

import itertools
import random
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pytest
from fastapi import FastAPI
from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.validation import quote_lines
from app.db.models import Language, MarkDecision, Page
from app.redpen.align import align
from app.redpen.ink import Band, detect_lines
from app.redpen.layout import CROSS, TICK, PointMark, QuestionMarks, layout_page, question_starts
from tests.conftest import World
from tests.factories import ApiUser, Factory, make_ready_exam, run_jobs, start_ai, upload_pdf
from tests.scan_builder import ScanBuilder, render_pdf_pages

ANSWER = [
    "1(a) Metals conduct electricity and they are",
    "malleable.",
    "",
    "1(b) Hydrogen gas H_2 is given off.",
]


def written_page(lines: list[str], seed: int = 1) -> Image.Image:
    """A ruled page with one scribbled line per text line, as long as the text."""
    rng = random.Random(seed)  # noqa: S311 - deterministic test data
    width, height = 1240, 1754
    image = Image.new("RGB", (width, height), (250, 250, 247))
    draw = ImageDraw.Draw(image)
    for y in range(180, height - 20, 54):
        draw.line([(0, y), (width, y)], fill=(170, 190, 215), width=1)
    draw.line([(160, 0), (160, height)], fill=(220, 120, 120), width=2)
    y = 214
    for text in lines:
        x = 190
        end = x + len(text) * 19
        while text and x < end:
            word = min(rng.randint(40, 110), end - x)
            points = [(x + i * 4, y + rng.randint(-12, 4)) for i in range(max(word // 4, 2))]
            draw.line(points, fill=(30, 40, 140), width=3)
            x += word + rng.randint(14, 26)
        y += 54
    return image.filter(ImageFilter.GaussianBlur(0.6))


# --- finding the lines and matching them ------------------------------------------------------


def test_lines_of_writing_are_found_in_order_and_sized() -> None:
    bands = detect_lines(written_page(ANSWER))
    assert len(bands) == 3  # the blank line has no ink
    assert [round(b.top, 2) < round(n.top, 2) for b, n in itertools.pairwise(bands)] == [
        True,
        True,
    ]
    assert bands[1].width < bands[0].width / 3  # "malleable." is short


def test_transcription_lines_match_the_ink_one_to_one() -> None:
    bands = detect_lines(written_page(ANSWER))
    alignment = align(ANSWER, bands)
    assert alignment is not None
    assert alignment.confident
    assert alignment.lines == {0: (0, 0), 1: (1, 1), 3: (2, 2)}


def test_a_line_the_reader_joined_covers_two_lines_of_ink() -> None:
    bands = detect_lines(written_page(ANSWER))
    joined = ["1(a) Metals conduct electricity and they are malleable.", "", ANSWER[3]]
    alignment = align(joined, bands)
    assert alignment is not None
    assert alignment.confident
    assert alignment.lines[0] == (0, 1)


def test_text_that_does_not_fit_the_page_is_not_trusted() -> None:
    bands = detect_lines(written_page(["x" * 40] * 9))
    alignment = align(["one short line", "and another"], bands)
    assert alignment is not None
    assert not alignment.confident


def test_quoted_evidence_is_found_in_the_answer_lines() -> None:
    lines = ["1(a) Metals conduct", "electricity well.", "1(b) Hydrogen"]
    assert quote_lines(lines, "conduct electricity") == (1, 2)
    assert quote_lines(lines, "HYDROGEN") == (3,)
    assert quote_lines(lines, "not there") == ()


def test_question_starts_follow_the_written_labels() -> None:
    text = ["1a) first", "more", "1(b) second", "2. third", "10) ten"]
    assert question_starts(text, ["1(a)", "1(b)", "2", "1"]) == {"1(a)": 0, "1(b)": 2, "2": 3}


# --- where marks go ---------------------------------------------------------------------------


def _bands() -> list[Band]:
    return [
        Band(top=0.10, bottom=0.12, left=0.15, right=0.70, ink=0.2),
        Band(top=0.13, bottom=0.15, left=0.15, right=0.30, ink=0.2),
        Band(top=0.30, bottom=0.32, left=0.15, right=0.95, ink=0.2),
    ]


def test_ticks_follow_their_evidence_and_crosses_the_question_start() -> None:
    text = ["1(a) long first line", "short", "1(b) a line to the edge"]
    alignment = align(text, _bands())
    assert alignment is not None
    questions = [
        QuestionMarks(
            1,
            "1(a)",
            "1/2",
            (PointMark(10, TICK, "", (1,)), PointMark(11, CROSS, "", ())),
            "Revise the second property.",
            earned_any=True,
        ),
        QuestionMarks(2, "1(b)", "1/1", (PointMark(20, TICK, "", (2,)),)),
    ]

    layout = layout_page(text, _bands(), alignment, questions, total="2/3")

    assert layout.placed
    by_point = {m.point_id: m for m in layout.marks if m.point_id}
    assert by_point[10].x == pytest.approx(0.32)  # just after "short" (its evidence line)
    assert by_point[10].y == pytest.approx(0.14)
    assert by_point[11].kind == CROSS
    assert by_point[11].y == pytest.approx(0.11)  # the one line of 1(a) that earned nothing
    # A line running to the edge: the tick goes just below its end, not over the words.
    assert by_point[20].y > 0.31
    assert by_point[20].x + 0.01 < 0.985
    scores = {m.text: m for m in layout.marks if m.kind == "score"}
    assert scores["1/2"].x < 0.15
    comment = next(m for m in layout.marks if m.kind == "comment")
    assert comment.y > 0.15  # in the blank space below question 1(a)
    assert any(m.kind == "total" and m.text == "2/3" for m in layout.marks)


# Line lengths that match _bands(), so the alignment is trusted.
FITTING = ["1(a) long first line", "short", "1(b) a line to the edge"]


def _crosses(questions: list[QuestionMarks], text: list[str]) -> list[float]:
    alignment = align(text, _bands())
    assert alignment is not None
    layout = layout_page(text, _bands(), alignment, questions)
    assert layout.placed
    assert any(m.kind == TICK or m.kind == "score" for m in layout.marks)  # really placed
    return [m.y for m in layout.marks if m.kind == CROSS]


def test_a_cross_goes_on_the_first_line_when_the_answer_earned_nothing() -> None:
    text = FITTING
    points = (PointMark(10, CROSS, "", ()), PointMark(11, CROSS, "", ()))
    crosses = _crosses([QuestionMarks(1, "1(a)", "0/2", points)], text)
    assert crosses == [pytest.approx(0.11)] * 2  # both beside the first line


def test_no_cross_when_more_than_one_line_earned_nothing() -> None:
    text = FITTING  # with only 1(a) asked for, all three lines are its answer
    points = (PointMark(10, TICK, "", (0,)), PointMark(11, CROSS, "", ()))
    assert _crosses([QuestionMarks(1, "1(a)", "1/2", points, earned_any=True)], text) == []


def test_a_cross_never_goes_on_a_line_that_earned_a_mark() -> None:
    text = FITTING
    points = (
        PointMark(10, TICK, "", (0,)),
        PointMark(11, TICK, "", (1,)),
        PointMark(12, TICK, "", (2,)),
        PointMark(13, CROSS, "", ()),
    )
    assert _crosses([QuestionMarks(1, "1(a)", "3/4", points, earned_any=True)], text) == []


def test_a_cross_goes_on_the_only_line_that_earned_nothing() -> None:
    points = (PointMark(10, TICK, "", (0,)), PointMark(11, CROSS, "", ()))
    questions = [
        QuestionMarks(1, "1(a)", "1/2", points, earned_any=True),
        QuestionMarks(2, "1(b)", "1/1", (PointMark(20, TICK, "", (2,)),), earned_any=True),
    ]
    assert _crosses(questions, FITTING) == [pytest.approx(0.14)]  # "short", line 2 of 1(a)


def test_a_point_with_no_evidence_line_gets_no_tick() -> None:
    text = FITTING
    alignment = align(text, _bands())
    assert alignment is not None
    points = (PointMark(10, TICK, "", ()),)
    layout = layout_page(
        text, _bands(), alignment, [QuestionMarks(1, "1(a)", "1/1", points, earned_any=True)]
    )
    assert [m for m in layout.marks if m.kind == TICK] == []
    assert any(m.kind == "score" and m.text == "1/1" for m in layout.marks)


def test_an_unsure_match_places_nothing_and_keeps_comments_for_the_margin() -> None:
    text = ["1(a) x"]
    questions = [QuestionMarks(1, "1(a)", "0/1", (PointMark(10, CROSS, "", ()),), "See me.")]
    layout = layout_page(text, _bands(), None, questions)
    assert not layout.placed
    assert layout.marks == []
    assert [q.comment for q in layout.unplaced_comments] == ["See me."]


# --- end to end -------------------------------------------------------------------------------


@pytest.fixture
def alice(app: FastAPI, world: World) -> ApiUser:
    return ApiUser(app, "alice")


@pytest.fixture
def marked(
    app: FastAPI, alice: ApiUser, world: World, factory: Factory, db: Session, settings: Any
) -> int:
    """One script whose page and transcription match (Mock models, line evidence)."""
    factory.student(world.class_a, "AAAAAA", "Ama Fon")
    exam = make_ready_exam(alice, world.class_a.id)
    alice.post(f"/api/exams/{exam['id']}/cover-sheets")
    cover = render_pdf_pages(alice.get(f"/api/exams/{exam['id']}/cover-sheets.pdf").content)[0]
    upload_pdf(alice, exam["id"], ScanBuilder().add(cover).add(written_page(ANSWER)).build())
    page = db.scalars(select(Page).where(Page.is_cover.is_(False))).one()
    # The Mock reader returns the text stored next to the page image.
    (settings.data_dir / page.image_path).with_suffix(".txt").write_text(
        "\n".join(ANSWER), encoding="utf-8"
    )
    start_ai(alice, exam["id"])
    run_jobs(app)
    return int(db.scalar(select(MarkDecision.script_id)) or 0)


def test_the_worker_records_where_each_proposals_evidence_is(marked: int, db: Session) -> None:
    page_id = db.scalar(select(Page.id).where(Page.is_cover.is_(False)))
    refs = [d.evidence_refs for d in db.scalars(select(MarkDecision).order_by(MarkDecision.id))]
    assert refs == [[[page_id, 0]], [[page_id, 1]], [[page_id, 3]]]


def test_the_red_pen_is_placed_beside_the_answers(alice: ApiUser, marked: int, db: Session) -> None:
    body = alice.get(f"/api/scripts/{marked}/red-pen").json()
    [page] = body["pages"]
    assert page["placed"] is True
    kinds = [m["kind"] for m in page["marks"]]
    assert kinds.count("tick") == 3
    assert sorted(m["text"] for m in page["marks"] if m["kind"] == "score") == ["1/1", "2/2"]
    assert body["total"] == "3/3"
    assert all(m["pending"] for m in page["marks"] if m["kind"] == "tick")  # not decided yet


def test_the_marked_pdf_carries_the_red_pen_and_comments(
    alice: ApiUser, marked: int, db: Session
) -> None:
    question = alice.get(f"/api/scripts/{marked}/review").json()["questions"][0]["id"]
    alice.put(
        f"/api/scripts/{marked}/questions/{question}/comment", json={"text": "Bien vu, élève."}
    )
    alice.post(f"/api/scripts/{marked}/accept-all")
    alice.post(f"/api/scripts/{marked}/confirm")

    content = alice.get(f"/api/scripts/{marked}/marked.pdf").content

    pdf = pdfium.PdfDocument(content)
    try:
        answer_page = pdf[1].get_textpage().get_text_range()
    finally:
        pdf.close()
    assert "2/2" in answer_page  # the question score, handwritten beside the answer
    assert "3/3" in answer_page  # the circled total
    assert "Bien vu, élève." in answer_page
    assert b"Caveat" in content


def _pdf_text(content: bytes) -> list[str]:
    pdf = pdfium.PdfDocument(content)
    try:
        return [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
    finally:
        pdf.close()


def _confirm_with_a_missed_point(alice: ApiUser, script_id: int) -> None:
    review = alice.get(f"/api/scripts/{script_id}/review").json()
    question = review["questions"][1]
    alice.post(f"/api/scripts/{script_id}/accept-all")
    alice.put(
        f"/api/scripts/{script_id}/decisions/{question['points'][0]['id']}", json={"marks": 0}
    )
    alice.put(
        f"/api/scripts/{script_id}/questions/{question['id']}/comment",
        json={"text": "H_2 gives a squeaky pop; Zn + 2HCl -> ZnCl_2 + H_2"},
    )
    alice.post(f"/api/scripts/{script_id}/confirm")


def test_missed_points_print_only_when_the_exam_shows_the_scheme(
    alice: ApiUser, marked: int, db: Session
) -> None:
    _confirm_with_a_missed_point(alice, marked)
    exam_id = alice.get(f"/api/scripts/{marked}/review").json()["exam"]["id"]

    hidden = _pdf_text(alice.get(f"/api/scripts/{marked}/marked.pdf").content)[1]
    alice.put(f"/api/exams/{exam_id}/settings", json={"show_scheme_to_students": True})
    shown = _pdf_text(alice.get(f"/api/scripts/{marked}/marked.pdf").content)[1]

    assert "Missing:" not in hidden
    assert "Missing:" in shown
    # The teacher's own comment prints either way, with its notation written properly.
    for text in (hidden, shown):
        assert "H₂ gives a squeaky pop" in text
        assert "ZnCl₂" in text


def test_every_page_has_the_footer_and_only_the_cover_has_the_summary(
    alice: ApiUser, marked: int, db: Session, world: World
) -> None:
    _confirm_with_a_missed_point(alice, marked)

    cover, answer = _pdf_text(alice.get(f"/api/scripts/{marked}/marked.pdf").content)
    world.teacher_a.preferred_language = Language.FR
    db.commit()
    cover_fr, answer_fr = _pdf_text(alice.get(f"/api/scripts/{marked}/marked.pdf").content)

    name = world.teacher_a.display_name
    for page in (cover, answer):
        assert f"reviewed and confirmed by {name}" in " ".join(page.split())
    for page in (cover_fr, answer_fr):
        assert f"revu et confirmé par {name}" in " ".join(page.split())
    assert "Results" in cover
    assert "Results" not in answer


def test_another_teacher_cannot_see_the_red_pen(app: FastAPI, world: World, marked: int) -> None:
    assert ApiUser(app, "bruno").get(f"/api/scripts/{marked}/red-pen").status_code == 404


def test_written_page_helper_draws_lines_as_long_as_the_text(tmp_path: Path) -> None:
    page = written_page(["x" * 10, "x" * 30])
    page.save(tmp_path / "p.png")
    bands = detect_lines(page)
    assert bands[1].width > bands[0].width * 2
