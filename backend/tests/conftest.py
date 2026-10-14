import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

INDEX_HTML = "<!doctype html><html><body><div id='root'></div></body></html>"


@pytest.fixture(autouse=True)
def _close_log_handlers() -> Iterator[None]:
    """Detach file handlers after each test so temporary directories can be removed on Windows."""
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)
            handler.close()


@pytest.fixture
def frontend_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok');", encoding="utf-8")
    return dist


@pytest.fixture
def settings(tmp_path: Path, frontend_dist: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        data_dir=tmp_path / "data",
        frontend_dist=frontend_dist,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
