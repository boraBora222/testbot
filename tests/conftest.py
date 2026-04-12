import os
from pathlib import Path
import sys
from collections.abc import AsyncIterator, Callable, Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_TEST_ENV = {
    "MONGO_DB_NAME": "test_db",
    "WEB_BASE_URL": "http://localhost:8000",
    "FRONT_BASE_URL": "http://localhost:5138",
    "TELEGRAM_BOT_TOKEN": "test-token",
    "MASTER_USER_IDS": "1,2",
    "WEB_USERNAME": "admin",
    "WEB_PASSWORD": "password",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "smtp-user",
    "SMTP_PASSWORD": "smtp-password",
    "SMTP_FROM_EMAIL": "no-reply@example.com",
    "SMTP_USE_SSL": "false",
    "SMTP_USE_TLS": "true",
    "AUTH_COOKIE_NAME": "cryptodeal_session",
    "AUTH_COOKIE_SECURE": "false",
    "AUTH_COOKIE_SAMESITE": "lax",
    "WEB_REGISTRATION_DEFAULT_VERIFICATION_LEVEL": "basic",
    "WEB_REGISTRATION_DEFAULT_DAILY_LIMIT": "1000000",
    "WEB_REGISTRATION_DEFAULT_MONTHLY_LIMIT": "5000000",
}

for env_key, env_value in _TEST_ENV.items():
    os.environ[env_key] = env_value


@pytest.fixture(autouse=True)
def clear_auth_state() -> Iterator[None]:
    from shared import db

    db._web_users.clear()
    db._auth_sessions.clear()
    db._exchange_users.clear()
    db._bot_users.clear()
    db._limit_quotas.clear()
    db._limit_quota_history.clear()
    yield
    db._web_users.clear()
    db._auth_sessions.clear()
    db._exchange_users.clear()
    db._bot_users.clear()
    db._limit_quotas.clear()
    db._limit_quota_history.clear()


@pytest.fixture
def client_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], TestClient]]:
    import web.main as web_main

    async def _noop() -> None:
        return None

    monkeypatch.setattr(web_main.db, "connect_db", _noop)
    monkeypatch.setattr(web_main.db, "disconnect_db", _noop)
    monkeypatch.setattr(web_main.redis_client, "connect_redis", _noop)
    monkeypatch.setattr(web_main.redis_client, "disconnect_redis", _noop)

    clients: list[TestClient] = []

    def build_client() -> TestClient:
        client = TestClient(web_main.app)
        client.__enter__()
        clients.append(client)
        return client

    yield build_client

    while clients:
        client = clients.pop()
        client.__exit__(None, None, None)


@pytest.fixture
def app_client(client_factory: Callable[[], TestClient]) -> Iterator[TestClient]:
    client = client_factory()
    yield client


@pytest.fixture
def auth_app() -> FastAPI:
    from web.routers.auth import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    return app


@pytest.fixture
async def auth_async_client(auth_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=auth_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def captured_email_codes(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, str]]:
    import web.routers.auth as auth_router

    captured_codes = {
        "verification": {},
        "reset": {},
    }

    async def fake_send_verification_code(email: str, code: str) -> None:
        captured_codes["verification"][email] = code

    async def fake_send_password_reset_code(email: str, code: str) -> None:
        captured_codes["reset"][email] = code

    monkeypatch.setattr(auth_router, "send_verification_code_email", fake_send_verification_code)
    monkeypatch.setattr(auth_router, "send_password_reset_code_email", fake_send_password_reset_code)

    return captured_codes
