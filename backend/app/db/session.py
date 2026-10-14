from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    # WAL: readers do not block the writer (web app and worker share the file).
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    # NORMAL is durable across application crashes; with WAL it is the recommended setting.
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def make_engine(settings: Settings) -> Engine:
    url = settings.resolved_database_url
    if url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _configure_sqlite)
        return engine
    return create_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
