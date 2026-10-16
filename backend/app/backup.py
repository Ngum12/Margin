"""Backup and restore of a Margin installation (Phase 6): the database and every stored file
(uploads, page images, exports) in one zip. Logs and earlier backups are left out.

The SQLite database is copied with SQLite's online backup, so a backup can run while the app and
the worker are running. Restoring needs the app and the worker stopped."""

import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings

DB_NAME = "margin.db"
SKIP = {"logs", "backups"}


def _sqlite_path(settings: Settings) -> Path:
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("Backups cover the built-in SQLite database only.")
    return Path(url.removeprefix("sqlite:///"))


def backup(settings: Settings, out: Path | None = None) -> Path:
    data = settings.data_dir
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = out or data / "backups" / f"margin-backup-{stamp}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    db_path = _sqlite_path(settings)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / DB_NAME
        source = sqlite3.connect(db_path)
        dest = sqlite3.connect(copy)
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(copy, DB_NAME)
            for path in sorted(data.rglob("*")):
                relative = path.relative_to(data)
                if not path.is_file() or relative.parts[0] in SKIP:
                    continue
                if relative.name.startswith(DB_NAME):  # the live database and its WAL files
                    continue
                archive.write(path, relative.as_posix())
    return target


def restore(settings: Settings, archive_path: Path, *, force: bool = False) -> None:
    data = settings.data_dir
    db_path = _sqlite_path(settings)
    if db_path.exists() and not force:
        raise FileExistsError(
            f"{db_path} exists. Stop Margin and pass --force to replace the current data."
        )
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if DB_NAME not in names:
            raise ValueError("This file is not a Margin backup (no margin.db inside).")
        root = data.resolve()
        for name in names:
            if not (root / name).resolve().is_relative_to(root):
                raise ValueError(f"Unsafe path in backup: {name}")
        for suffix in ("", "-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
        data.mkdir(parents=True, exist_ok=True)
        for name in names:
            if name == DB_NAME:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_path.write_bytes(archive.read(name))
            else:
                archive.extract(name, data)
