"""Migrations must produce exactly the schema the models describe."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db import models  # noqa: F401  (registers tables)
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def test_upgrade_head_matches_models_and_downgrade_works(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}")
    config = _alembic_config()

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()


def test_migration_check_constraints_are_not_duplicated(tmp_path: Path) -> None:
    """Alembic autogenerate emits each enum CHECK twice; migrations must keep only the named one."""
    engine = create_engine(f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}")
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    inspector = inspect(engine)
    checks = {
        table: sorted(str(c["name"]) for c in inspector.get_check_constraints(table))
        for table in inspector.get_table_names()
    }
    assert checks["user"] == ["ck_user_preferred_language", "ck_user_role"]
    assert checks["page"] == [
        "ck_page_page_state",
        "ck_page_unassigned_reason",
    ]
    for table, names in checks.items():
        assert all(name.startswith(f"ck_{table}_") for name in names), (table, names)
    engine.dispose()
