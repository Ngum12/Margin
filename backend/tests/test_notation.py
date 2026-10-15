import pytest

from app.exports import fonts
from app.exports.notation import pretty


@pytest.mark.parametrize(
    ("typed", "printed"),
    [
        ("CH_4", "CH₄"),
        ("x^2 + y^2", "x² + y²"),
        ("Na^+ and SO_4^2-", "Na⁺ and SO₄²⁻"),
        ("N_2 + 3H_2 <=> 2NH_3", "N₂ + 3H₂ ⇌ 2NH₃"),
        ("Ca(OH)_2 -> milky", "Ca(OH)₂ → milky"),
        ("10^-3 and x_{12}", "10⁻³ and x₁₂"),
        ("snake_case and plain text", "snake_case and plain text"),
    ],
)
def test_typed_notation_prints_as_symbols(typed: str, printed: str) -> None:
    assert pretty(typed) == printed


def test_every_printed_symbol_has_a_font_or_is_drawn() -> None:
    text = pretty("SO_4^2- + Na^+ -> x^n <=> CH_4 ✓ ✗ é")
    assert fonts.printable(text, fonts.HANDWRITING) == text
    assert fonts.text_width("→", fonts.HANDWRITING, 10) == pytest.approx(10)
