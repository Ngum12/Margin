"""Migrations must produce exactly the schema the models describe."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.db.models import Page
from app.db.session import make_engine

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


def test_upgrade_works_on_a_database_with_data_and_foreign_keys_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner's installation, 2026-10-15: migration 0007 rebuilds the exam table, which SQLite
    refused while scripts referred to it. Upgrades now run with foreign keys off and check
    every reference afterwards. Runs through the app's own engine (foreign keys on)."""
    monkeypatch.setenv("MARGIN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MARGIN_ENV", "test")
    get_settings.cache_clear()
    try:
        config = _alembic_config()
        command.upgrade(config, "0006")
        engine = make_engine(get_settings())
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            connection.exec_driver_sql(
                "INSERT INTO school (id, name, country, curriculum, created_at, updated_at)"
                " VALUES (1, 'S', 'Cameroon', 'cm_gce_ol', '2026-10-01', '2026-10-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO user (id, school_id, username, display_name, password_hash, role,"
                " preferred_language, is_active, created_at, updated_at) VALUES"
                " (1, 1, 'alice', 'Alice', 'x', 'teacher', 'en', 1, '2026-10-01', '2026-10-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO school_class (id, school_id, name, academic_year, teacher_id,"
                " created_at, updated_at)"
                " VALUES (1, 1, '5A', '2026', 1, '2026-10-01', '2026-10-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO student (id, school_id, class_id, code, training_consent,"
                " created_at, updated_at) VALUES (1, 1, 1, 'AAAAAA', 0, '2026-10-01', '2026-10-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO exam (id, class_id, subject_code, title, status, created_by_id,"
                " created_at, updated_at) VALUES"
                " (1, 1, 'chemistry', 'T', 'reviewing', 1, '2026-10-01', '2026-10-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO script (id, exam_id, student_id, status, ai_run, created_at,"
                " updated_at) VALUES (1, 1, 1, 'ai_marked', 0, '2026-10-01', '2026-10-01')"
            )
        engine.dispose()

        command.upgrade(config, "head")

        engine = make_engine(get_settings())
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM script").scalar() == 1
            assert connection.exec_driver_sql("SELECT title FROM exam").scalar() == "T"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            tables = {
                row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master")
            }
            assert not any(name.startswith("_alembic_tmp") for name in tables)
        engine.dispose()
    finally:
        get_settings.cache_clear()
