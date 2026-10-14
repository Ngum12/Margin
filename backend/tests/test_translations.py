"""Every error and issue code the backend can send must have English and French text in the
frontend, so teachers never see a raw code."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app import errors

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "backend" / "app"
LOCALES = REPO / "frontend" / "src" / "i18n" / "locales"

_CODE_PATTERNS = [
    re.compile(r'code="([a-z_.]+)"'),  # DomainError(..., code="x.y")
    re.compile(r'Issue\(\s*"([a-z_.]+)"'),  # Issue("x.y", ...)
    re.compile(r'_row_issue\(\s*"([a-z_.]+)"'),
]


def _source_codes() -> tuple[set[str], set[str]]:
    """(error codes, issue codes) found in backend source."""
    error_codes = {
        cls.default_code
        for cls in vars(errors).values()
        if isinstance(cls, type) and issubclass(cls, errors.DomainError)
    }
    issue_codes: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        error_codes.update(_CODE_PATTERNS[0].findall(text))
        for pattern in _CODE_PATTERNS[1:]:
            issue_codes.update(pattern.findall(text))
    error_codes.discard("error")  # base class default, never raised directly
    return error_codes, issue_codes


def _lookup(tree: dict[str, Any], dotted: str) -> object:
    node: object = tree
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@pytest.mark.parametrize("language", ["en", "fr"])
def test_all_backend_codes_are_translated(language: str) -> None:
    locale = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    error_codes, issue_codes = _source_codes()

    missing_errors = sorted(
        c for c in error_codes if not isinstance(_lookup(locale["errors"], c), str)
    )
    missing_issues = sorted(
        c for c in issue_codes if not isinstance(_lookup(locale["issues"], c), str)
    )

    assert missing_errors == []
    assert missing_issues == []
    assert len(issue_codes) > 20  # the scan really found the codes
