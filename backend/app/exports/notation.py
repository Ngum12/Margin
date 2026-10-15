"""Print Margin's typed notation as proper symbols (owner, 2026-10-15): CH_4 → CH₄, x^2 → x²,
Na^+ → Na⁺, -> → →, <=> → ⇌. Used for text printed on marked scripts (comments, notes)."""

import re

_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SUP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")

_BRACED_SUB = re.compile(r"_\{([0-9+\-=()]+)\}")
_BRACED_SUP = re.compile(r"\^\{([0-9+\-=()n]+)\}")
_SUB_RUN = re.compile(r"(?<=[A-Za-z)\]])_([0-9]+)")
_SUP_RUN = re.compile(r"\^([+\-]?[0-9]+[+\-]?|[+\-]|n)")


def pretty(text: str) -> str:
    text = text.replace("<=>", "⇌").replace("->", "→")
    text = _BRACED_SUB.sub(lambda m: m.group(1).translate(_SUB), text)
    text = _BRACED_SUP.sub(lambda m: m.group(1).translate(_SUP), text)
    text = _SUB_RUN.sub(lambda m: m.group(1).translate(_SUB), text)
    return _SUP_RUN.sub(lambda m: m.group(1).translate(_SUP), text)
