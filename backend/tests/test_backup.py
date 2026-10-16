import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app import backup
from app.config import Settings


def _settings(data: Path) -> Settings:
    return Settings(_env_file=None, env="test", data_dir=data)


def _make_install(data: Path) -> None:
    (data / "uploads" / "1").mkdir(parents=True)
    (data / "uploads" / "1" / "original.pdf").write_bytes(b"%PDF-1.7 test")
    (data / "logs").mkdir()
    (data / "logs" / "app.log").write_text("not backed up", encoding="utf-8")
    # closing(): sqlite3's own context manager commits but leaves the file open (locked on Windows).
    with closing(sqlite3.connect(data / "margin.db")) as db, db:
        db.execute("create table t (v text)")
        db.execute("insert into t values ('kept')")


def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "a"
    _make_install(source)
    archive = backup.backup(_settings(source), tmp_path / "b.zip")

    target = tmp_path / "restored"
    backup.restore(_settings(target), archive)

    assert (target / "uploads" / "1" / "original.pdf").read_bytes() == b"%PDF-1.7 test"
    assert not (target / "logs").exists()
    with closing(sqlite3.connect(target / "margin.db")) as db:
        assert db.execute("select v from t").fetchall() == [("kept",)]


def test_restore_never_overwrites_without_force(tmp_path: Path) -> None:
    source = tmp_path / "a"
    _make_install(source)
    archive = backup.backup(_settings(source), tmp_path / "b.zip")
    with pytest.raises(FileExistsError):
        backup.restore(_settings(source), archive)
    backup.restore(_settings(source), archive, force=True)


def test_restore_refuses_a_zip_that_is_not_a_backup(tmp_path: Path) -> None:
    import zipfile

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../evil.txt", "x")
    with pytest.raises(ValueError, match="not a Margin backup"):
        backup.restore(_settings(tmp_path / "t"), bad)
