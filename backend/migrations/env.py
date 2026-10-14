"""Alembic environment. Uses the app's settings and models; batch mode for SQLite ALTERs."""

from alembic import context
from sqlalchemy import Connection

from app.config import get_settings
from app.db import models  # noqa: F401  (registers all tables)
from app.db.base import Base
from app.db.session import make_engine

target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = make_engine(get_settings())
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline SQL generation is not supported; run against a database.")
run_migrations_online()
