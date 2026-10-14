import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.base import Base
from app.db.models import Role, School, SchoolClass, User
from app.main import create_app
from tests.factories import Factory

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
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings, inline_upload_processing=True)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(app: FastAPI) -> Iterator[Session]:
    with app.state.sessionmaker() as session:
        yield session


@pytest.fixture
def factory(db: Session) -> Factory:
    return Factory(db)


@dataclass
class World:
    school: School
    admin: User
    teacher_a: User
    teacher_b: User
    class_a: SchoolClass
    class_b: SchoolClass


@pytest.fixture
def world(factory: Factory) -> World:
    """One school: an admin and two teachers, each teacher with one class."""
    school = factory.school()
    admin = factory.user(school, "admin", Role.ADMIN)
    teacher_a = factory.user(school, "alice")
    teacher_b = factory.user(school, "bruno")
    return World(
        school=school,
        admin=admin,
        teacher_a=teacher_a,
        teacher_b=teacher_b,
        class_a=factory.school_class(school, teacher_a, "Form 5A"),
        class_b=factory.school_class(school, teacher_b, "Form 5B"),
    )
