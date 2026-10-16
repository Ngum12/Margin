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


def test_backup_in_data_directory_does_not_include_itself(tmp_path: Path) -> None:
    import json
    import zipfile

    source = tmp_path / "school"
    _make_install(source)
    target = source / "manual.zip"
    backup.backup(_settings(source), target)
    with zipfile.ZipFile(target) as archive:
        assert "manual.zip" not in archive.namelist()
        assert not any(name.endswith(".partial") for name in archive.namelist())
        manifest = json.loads(archive.read("backup-manifest.json"))
        assert "margin.db" in manifest["sha256"]


@pytest.mark.parametrize(
    "unsafe", ["../escape", "C:/escape", "folder\\escape", "CON.txt", "file:stream"]
)
def test_restore_rejects_unsafe_paths_before_touching_existing_data(
    tmp_path: Path, unsafe: str
) -> None:
    import zipfile

    source = tmp_path / "school"
    _make_install(source)
    original = (source / "margin.db").read_bytes()
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("margin.db", b"not a database")
        archive.writestr(unsafe, b"untrusted")
    with pytest.raises(ValueError, match=r"Unsafe path|Windows device"):
        backup.restore(_settings(source), bad, force=True)
    assert (source / "margin.db").read_bytes() == original


def test_corrupt_backup_never_replaces_live_data_and_success_keeps_rollback(tmp_path: Path) -> None:
    import json
    import zipfile

    source = tmp_path / "school"
    _make_install(source)
    original = (source / "margin.db").read_bytes()
    valid = backup.backup(_settings(source), tmp_path / "valid.zip")
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(valid) as archive, zipfile.ZipFile(bad, "w") as changed:
        for name in archive.namelist():
            content = archive.read(name)
            if name == "backup-manifest.json":
                manifest = json.loads(content)
                manifest["sha256"]["margin.db"] = "0" * 64
                content = json.dumps(manifest).encode()
            changed.writestr(name, content)
    with pytest.raises(ValueError, match="checksum"):
        backup.restore(_settings(source), bad, force=True)
    assert (source / "margin.db").read_bytes() == original
    backup.restore(_settings(source), valid, force=True)
    previous = list(tmp_path.glob("school.before-restore-*"))
    assert len(previous) == 1
    assert (previous[0] / "margin.db").read_bytes() == original
