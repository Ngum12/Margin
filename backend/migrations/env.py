"""Alembic environment. Uses the app's settings and models; batch mode for SQLite ALTERs.

SQLite: the app connects with foreign keys enforced. Batch mode rebuilds a table by copying it
and dropping the original, which SQLite refuses while other rows refer to it (seen on the
owner's data, 2026-10-15). So foreign keys are switched off for the upgrade and every
relationship is checked afterwards; the upgrade fails if any is broken.
"""

from alembic import context
from sqlalchemy import Connection

from app.config import get_settings
from app.db import models  # noqa: F401  (registers all tables)
from app.db.base import Base
from app.db.session import make_engine

target_metadata = Base.metadata


class ForeignKeyCheckError(RuntimeError):
    """The upgrade would leave rows pointing at rows that do not exist."""


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )


def _run(connection: Connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Must run outside a transaction, or SQLite ignores it.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    try:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
            if sqlite:
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise ForeignKeyCheckError(f"Broken references after upgrade: {broken[:5]}")
    finally:
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        # Tests pass their own connection (inside their transaction).
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = make_engine(get_settings())
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline SQL generation is not supported; run against a database.")
run_migrations_online()
