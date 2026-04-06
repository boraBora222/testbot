from base64 import b64encode

from fastapi.testclient import TestClient

from web.config import settings


def _authorization_header(username: str, password: str) -> dict[str, str]:
    token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_cors_preflight_allows_configured_origin_and_credentials(app_client: TestClient) -> None:
    response = app_client.options(
        "/auth/login",
        headers={
            "Origin": settings.front_base_url,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.front_base_url
    assert response.headers["access-control-allow-credentials"] == "true"


def test_moderator_basic_auth_protects_docs(app_client: TestClient) -> None:
    unauthorized_response = app_client.get("/docs")
    assert unauthorized_response.status_code == 401

    authorized_response = app_client.get(
        "/docs",
        headers=_authorization_header("admin", "password"),
    )
    assert authorized_response.status_code == 200
    assert "text/html" in authorized_response.headers["content-type"]
