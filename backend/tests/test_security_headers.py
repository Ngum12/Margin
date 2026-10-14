import pytest
from fastapi.testclient import TestClient

from app.security_headers import SECURITY_HEADERS


@pytest.mark.parametrize("path", ["/api/health", "/", "/assets/app.js", "/api/missing"])
def test_security_headers_on_every_response(client: TestClient, path: str) -> None:
    response = client.get(path)

    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


def test_csp_allows_only_same_origin(client: TestClient) -> None:
    csp = client.get("/").headers["Content-Security-Policy"]

    assert "default-src 'self'" in csp
    assert "http" not in csp


def test_api_docs_disabled_outside_development(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404
