"""Which scripts carry output from a test model (owner, 2026-10-15).

The Mock models are for tests and demonstrations without a GPU. Their output must never be
mistaken for real AI marking, so every screen and export that shows it labels it. A script is
flagged when any of its current mark decisions, or the current transcription of any of its
pages, came from a test model.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Transcription
from app.services.decisions import current_decisions

# Names given to the Mock models (app.ai.mock); real models never start with this.
TEST_MODEL_PREFIX = "mock-"


def is_test_model(name: str | None) -> bool:
    return name is not None and name.startswith(TEST_MODEL_PREFIX)


def test_model_scripts(db: Session, script_ids: Iterable[int]) -> set[int]:
    ids = list(script_ids)
    if not ids:
        return set()
    flagged = {
        script_id
        for (script_id, _point), decision in current_decisions(db, ids).items()
        if is_test_model(decision.model_name)
    }
    current: dict[int, Transcription] = {}
    for row in db.scalars(
        select(Transcription)
        .where(Transcription.script_id.in_(ids))
        .order_by(Transcription.created_at, Transcription.id)
    ):
        current[row.page_id] = row  # the newest version of each page wins
    flagged |= {row.script_id for row in current.values() if is_test_model(row.model_name)}
    return flagged


def marker_models(db: Session, script_ids: Iterable[int]) -> dict[int, list[str]]:
    """Per script, the distinct models behind its current AI proposals."""
    found: dict[int, set[str]] = {}
    for (script_id, _point), decision in current_decisions(db, list(script_ids)).items():
        if decision.model_name:
            found.setdefault(script_id, set()).add(decision.model_name)
    return {script_id: sorted(names) for script_id, names in found.items()}
