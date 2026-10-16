"""Every error and issue code the backend can send must have English and French text in the
frontend, so teachers never see a raw code."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app import errors
from app.db.models import UnassignedReason
from app.services.page_counts import PageCountFlag

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "backend" / "app"
LOCALES = REPO / "frontend" / "src" / "i18n" / "locales"

_CODE_PATTERNS = [
    re.compile(r'\bcode="([a-z_.]+)"'),  # DomainError(..., code="x.y"); not subject_code=
    re.compile(r'Issue\(\s*"([a-z_.]+)"'),  # Issue("x.y", ...)
    re.compile(r'_row_issue\(\s*"([a-z_.]+)"'),
]
# Upload failure codes are passed around as plain strings (RenderError, _mark_failed).
_UPLOAD_ERROR = re.compile(
    r'(?:RenderError\(|_mark_failed\(factory, upload_id,)\s*"(upload\.[a-z_]+)"'
)


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
        error_codes.update(_UPLOAD_ERROR.findall(text))
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


@pytest.mark.parametrize("language", ["en", "fr"])
def test_every_tray_reason_is_translated(language: str) -> None:
    locale = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))

    missing = [
        r.value
        for r in UnassignedReason
        if not isinstance(_lookup(locale, f"scans.reason.{r.value}"), str)
    ]

    assert missing == []


@pytest.mark.parametrize("language", ["en", "fr"])
def test_every_page_count_flag_is_translated(language: str) -> None:
    locale = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))

    assert all(isinstance(_lookup(locale, f"scans.pageFlag.{f.value}"), str) for f in PageCountFlag)


_MANUAL_REASON = re.compile(r'_flag_manual\(db, script, "([a-z_.]+)"\)')


@pytest.mark.parametrize("language", ["en", "fr"])
def test_every_manual_marking_reason_is_translated(language: str) -> None:
    locale = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    reasons = {
        m for path in APP_DIR.rglob("*.py") for m in _MANUAL_REASON.findall(path.read_text("utf-8"))
    }

    assert len(reasons) >= 3
    assert [
        r for r in reasons if not isinstance(_lookup(locale, f"ai.manualReason.{r}"), str)
    ] == []
