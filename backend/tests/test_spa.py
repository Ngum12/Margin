from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.spa import NOT_BUILT_MESSAGE
from tests.conftest import INDEX_HTML


def test_root_serves_index(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"


def test_client_routes_fall_back_to_index(client: TestClient) -> None:
    response = client.get("/exams/42/setup")

    assert response.status_code == 200
    assert response.text == INDEX_HTML


def test_static_assets_are_served(client: TestClient) -> None:
    response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert "console.log" in response.text


def test_missing_asset_is_404(client: TestClient) -> None:
    assert client.get("/assets/missing.js").status_code == 404


def test_unknown_api_path_is_json_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


def test_path_traversal_is_refused(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")

    for path in ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt"]:
        response = client.get(path)
        assert "secret" not in response.text


def test_explains_when_frontend_not_built(settings: Settings, tmp_path: Path) -> None:
    unbuilt = settings.model_copy(update={"frontend_dist": tmp_path / "nowhere"})
    with TestClient(create_app(unbuilt)) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert response.text == NOT_BUILT_MESSAGE
