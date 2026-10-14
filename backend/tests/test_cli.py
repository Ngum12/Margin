from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import cli
from app.auth.passwords import verify_password
from app.config import get_settings
from app.db.models import AuditEvent, Role, School, User


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MARGIN_ENV", "test")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _session(data_dir: Path) -> Session:
    return Session(create_engine(f"sqlite:///{(data_dir / 'margin.db').as_posix()}"))


def test_setup_flow_creates_school_and_admin(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_PW", "a-long-password")

    assert cli.main(["migrate"]) == 0
    assert cli.main(["init-school", "--name", "GBHS Test", "--country", "Cameroon"]) == 0
    assert cli.main(["init-school", "--name", "Again", "--country", "Cameroon"]) == 1
    assert (
        cli.main(
            [
                "create-user",
                "--username",
                "Head",
                "--display-name",
                "Head Teacher",
                "--role",
                "admin",
                "--password-env",
                "ADMIN_PW",
            ]
        )
        == 0
    )

    with _session(data_dir) as db:
        assert db.scalars(select(School.name)).one() == "GBHS Test"
        user = db.scalars(select(User)).one()
        assert (user.username, user.role) == ("head", Role.ADMIN)
        assert verify_password(user.password_hash, "a-long-password")
        assert db.scalars(select(AuditEvent.actor_id)).one() is None


def test_create_user_rejects_short_password(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PW", "short")
    cli.main(["migrate"])
    cli.main(["init-school", "--name", "S", "--country", "C"])

    assert (
        cli.main(["create-user", "--username", "x1", "--display-name", "X", "--password-env", "PW"])
        == 1
    )
