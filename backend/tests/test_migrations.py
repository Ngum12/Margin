"""Migrations must produce exactly the schema the models describe."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.db import models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.db.models import Page

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


def test_legacy_cover_rotation_is_never_applied_twice(tmp_path: Path) -> None:
    """Owner change 3 (Phase 4): a Phase 2 cover image already turned upright keeps that angle
    in ``rotation_baked`` and gets no further rotation."""
    engine = create_engine(f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}")
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003")
        # Foreign keys are not enforced on this bare connection, so one page row is enough.
        connection.exec_driver_sql(
            "INSERT INTO page (id, upload_id, source_page_index, image_path, thumb_path, width,"
            " height, rotation_applied, is_cover, state, created_at) VALUES"
            " (1, 1, 0, 'p.jpg', 't.jpg', 10, 20, 180, 1, 'assigned', '2026-10-01 00:00:00'),"
            " (2, 1, 1, 'q.jpg', 'u.jpg', 10, 20, 0, 0, 'assigned', '2026-10-01 00:00:00')"
        )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    with Session(engine) as db:
        cover, answer = db.get_one(Page, 1), db.get_one(Page, 2)
        assert (cover.rotation_baked, cover.rotation_stack, cover.rotation_auto) == (180, 0, 0)
        assert cover.rotation_teacher is None
        assert cover.effective_rotation == 0
        assert (answer.rotation_baked, answer.effective_rotation) == (0, 0)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0003")
        restored = connection.exec_driver_sql("SELECT rotation_applied FROM page ORDER BY id")
        assert [row[0] for row in restored] == [180, 0]
    engine.dispose()
