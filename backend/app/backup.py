"""Local SQLite snapshots, checksummed file archives, and validation-before-replacement restore."""

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.config import Settings

DB_NAME = "margin.db"
MANIFEST = "backup-manifest.json"
SKIP = {"logs", "backups", "scan-inbox"}
CHUNK = 1024 * 1024


def _sqlite_path(settings: Settings) -> Path:
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("Backups cover the built-in SQLite database only.")
    return Path(url.removeprefix("sqlite:///"))


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(CHUNK):
            value.update(block)
    return value.hexdigest()


def backup(settings: Settings, out: Path | None = None) -> Path:
    data = settings.data_dir.resolve()
    db_path = _sqlite_path(settings).resolve()
    if not db_path.is_file():
        raise ValueError("No database to back up; initialise Margin first.")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = out or data / "backups" / f"margin-backup-{stamp}.zip"
    if target.suffix.lower() != ".zip" or target.is_symlink():
        raise ValueError("Choose a regular .zip backup destination.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.partial")
    manifest: dict[str, str] = {}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / DB_NAME
            with (
                closing(sqlite3.connect(db_path)) as source,
                closing(sqlite3.connect(copy)) as dest,
            ):
                source.backup(dest)
                if dest.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ValueError("Database integrity check failed.")
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(copy, DB_NAME)
                manifest[DB_NAME] = _digest(copy)
                for path in sorted(data.rglob("*")):
                    relative = path.relative_to(data)
                    if relative.parts[0] in SKIP:
                        continue
                    if path.is_symlink():
                        raise ValueError("Backup refused a symbolic link in the data directory.")
                    if not path.is_file() or path.resolve() in {
                        target.resolve(),
                        temporary.resolve(),
                        db_path,
                    }:
                        continue
                    if str(path.resolve()) in {str(db_path) + "-wal", str(db_path) + "-shm"}:
                        continue
                    if relative.as_posix() == MANIFEST:
                        continue
                    # Hash the exact bytes written, rather than reopening a possibly changing file.
                    checksum = hashlib.sha256()
                    with (
                        path.open("rb") as source,
                        archive.open(relative.as_posix(), "w", force_zip64=True) as member,
                    ):
                        while block := source.read(CHUNK):
                            member.write(block)
                            checksum.update(block)
                    manifest[relative.as_posix()] = checksum.hexdigest()
                archive.writestr(
                    MANIFEST, json.dumps({"version": 1, "sha256": manifest}, sort_keys=True)
                )
            with temporary.open("rb+") as saved:
                os.fsync(saved.fileno())
            temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _safe_name(info: zipfile.ZipInfo) -> str:
    name = info.filename.rstrip("/")
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
        or str(path) != name
        or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK
        or any(part.rstrip(". ") != part for part in path.parts)
    ):
        raise ValueError(f"Unsafe path in backup: {info.filename}")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }
    if any(part.split(".")[0].upper() in reserved for part in path.parts):
        raise ValueError("Windows device path in backup.")
    return name


def restore(settings: Settings, archive_path: Path, *, force: bool = False) -> None:
    data = settings.data_dir.resolve()
    db_path = _sqlite_path(settings).resolve()
    if db_path != data / DB_NAME:
        raise ValueError(
            "Restore into a standard data directory with its margin.db, "
            "then configure a custom path separately."
        )
    if data.exists() and any(data.iterdir()) and not force:
        raise FileExistsError(f"{data} contains data. Stop Margin and pass --force to replace it.")
    data.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="margin-restore-", dir=data.parent) as tmp:
        stage = Path(tmp) / "data"
        stage.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if DB_NAME not in archive.namelist():
                raise ValueError("This file is not a Margin backup (no margin.db inside).")
            names = [_safe_name(i) for i in entries]
            if len({n.casefold() for n in names}) != len(names):
                raise ValueError("Duplicate paths in backup.")
            if sum(i.file_size for i in entries) > shutil.disk_usage(data.parent).free:
                raise ValueError("Not enough free space to validate and restore this backup.")
            for info, name in zip(entries, names, strict=True):
                target = stage / name
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as dest:
                    shutil.copyfileobj(source, dest, CHUNK)
        manifest_path = stage / MANIFEST
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != 1 or not isinstance(manifest.get("sha256"), dict):
                raise ValueError("Invalid backup manifest.")
            actual = {
                p.relative_to(stage).as_posix()
                for p in stage.rglob("*")
                if p.is_file() and p != manifest_path
            }
            if actual != set(manifest["sha256"]):
                raise ValueError("Backup manifest does not match its files.")
            for name, expected in manifest["sha256"].items():
                if _digest(stage / name) != expected:
                    raise ValueError("Backup checksum mismatch.")
            manifest_path.unlink()
        # Older local backups still get ZIP CRC, path, free-space and SQLite integrity checks.
        with closing(sqlite3.connect(stage / DB_NAME)) as check:
            if check.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("Backup database integrity check failed.")
        previous = data.with_name(f"{data.name}.before-restore-{uuid4().hex[:12]}")
        moved = False
        try:
            if data.exists():
                data.replace(previous)
                moved = True
            stage.replace(data)
        except OSError:
            if moved and not data.exists():
                previous.replace(data)
            raise
        # Keep the previous installation beside the restored one for deliberate rollback.
