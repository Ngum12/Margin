import pytest
from PIL import Image

from app.pdf.cover_frame import has_cover_frame
from app.sheets.cover_pdf import SheetInfo, SheetStudent, build_cover_sheets_pdf
from app.sheets.tokens import PayloadProblem, new_token, parse_payload, payload_for
from tests.scan_builder import answer_page, erase_qr, render_pdf_pages


def test_payload_round_trip() -> None:
    token = new_token()
    payload = payload_for(token)

    assert payload.startswith("MA1-")
    assert len(token) == 16
    assert parse_payload(payload).token == token
    assert parse_payload(f"  {payload}\n").token == token


def test_tokens_are_random_and_not_ids() -> None:
    tokens = {new_token() for _ in range(1000)}

    assert len(tokens) == 1000
    assert not any(t.isdigit() for t in tokens)


def test_any_single_character_change_is_detected() -> None:
    # Fixed token: with a random one, a 20-bit checksum would miss a change about once in 2,000
    # runs (D-029 accepts that risk for misreads; a test must be deterministic).
    payload = payload_for("ABCDEFGHIJKLMNOP")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

    for i, char in enumerate(payload):
        if char == "-" or i < 4:
            continue
        for replacement in alphabet:
            if replacement == char:
                continue
            changed = payload[:i] + replacement + payload[i + 1 :]
            assert parse_payload(changed).token is None, changed


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com",
        "42",
        "MA2-AAAAAAAAAAAAAAAA-AAAA",
        "MA1-short-AAAA",
        "MA1-aaaaaaaaaaaaaaaa-aaaa",
    ],
)
def test_foreign_payloads_are_not_ours(text: str) -> None:
    assert parse_payload(text).problem is PayloadProblem.NOT_OURS


def test_bad_checksum_is_reported() -> None:
    token = new_token()
    bad = payload_for(token)[:-4] + ("AAAA" if not payload_for(token).endswith("AAAA") else "BBBB")

    assert parse_payload(bad).problem is PayloadProblem.BAD_CHECKSUM


@pytest.fixture(scope="module")
def cover() -> Image.Image:
    pdf = build_cover_sheets_pdf(
        SheetInfo("Mock", "Chemistry", "Chimie", "Form 5A", None),
        [SheetStudent("AAAAAA", new_token())],
    )
    return render_pdf_pages(pdf)[0]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_cover_frame_found_at_any_rotation(cover: Image.Image, rotation: int) -> None:
    assert has_cover_frame(cover.rotate(rotation, expand=True))


def test_cover_frame_found_without_qr_codes(cover: Image.Image) -> None:
    assert has_cover_frame(erase_qr(cover))


def test_cover_frame_survives_small_skew(cover: Image.Image) -> None:
    assert has_cover_frame(cover.rotate(1.5, expand=False, fillcolor="white"))


@pytest.mark.parametrize("seed", range(6))
def test_answer_pages_have_no_cover_frame(seed: int) -> None:
    assert not has_cover_frame(answer_page(seed))
    assert not has_cover_frame(answer_page(seed).rotate(90, expand=True))


def test_blank_page_has_no_cover_frame() -> None:
    assert not has_cover_frame(Image.new("RGB", (1240, 1754), "white"))
