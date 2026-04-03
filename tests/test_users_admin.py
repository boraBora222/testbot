import json
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote_plus

from fastapi.testclient import TestClient
import pytest

from shared.models import LimitQuotaDB
from shared.security_settings import next_daily_reset_at, next_monthly_reset_at
from shared.types.enums import VerificationLevel
from shared.config import settings


class _AsyncCursor:
    def __init__(self, items):
        self._items = list(items)
        self._iterator = iter(())

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self._items)

    def __aiter__(self):
        self._iterator = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeUsersCollection:
    def __init__(self, items):
        self._items = list(items)

    def find(self, query=None):
        if query and "telegram_user_id" in query and isinstance(query["telegram_user_id"], dict):
            allowed = set(query["telegram_user_id"].get("$in", []))
            filtered = [item for item in self._items if item["telegram_user_id"] in allowed]
            return _AsyncCursor(filtered)
        return _AsyncCursor(self._items)

    async def find_one(self, query, projection=None):
        for item in self._items:
            if item["telegram_user_id"] == query.get("telegram_user_id"):
                return item
        return None

    async def distinct(self, field_name: str):
        return [item[field_name] for item in self._items if field_name in item]


class _FakeDB:
    def __init__(self, users):
        self.users = _FakeUsersCollection(users)
        self.bot_users = _FakeUsersCollection([])


def test_get_pending_whitelist_page_renders_entries(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import web.routers.users as users_router

    fake_db = _FakeDB(
        [
            {
                "telegram_user_id": 321,
                "username": "alice",
                "first_name": "Alice",
            }
        ]
    )
    app_client.app.dependency_overrides[users_router.get_db] = lambda: fake_db

    async def fake_list_pending_whitelist_addresses(limit: int = 200):
        return [
            {
                "id": "wla_1",
                "user_id": 321,
                "network": "TRC-20",
                "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "label": "Treasury",
                "created_at": datetime.now(timezone.utc),
            }
        ]

    monkeypatch.setattr(users_router, "list_pending_whitelist_addresses", fake_list_pending_whitelist_addresses)

    response = app_client.get("/users/whitelist/pending", auth=("admin", "password"))

    app_client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Treasury" in response.text
    assert "wla_1" in response.text


def test_approve_whitelist_entry_redirects_with_success(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import web.routers.users as users_router

    async def fake_moderate_whitelist_address(whitelist_id: str, **kwargs):
        assert whitelist_id == "wla_1"
        assert kwargs["verified_by"] == "admin"
        return {"id": "wla_1"}

    monkeypatch.setattr(users_router, "moderate_whitelist_address", fake_moderate_whitelist_address)

    response = app_client.post(
        "/users/whitelist/wla_1/approve",
        auth=("admin", "password"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "wla_1 approved" in unquote_plus(response.headers["location"])


def test_save_user_limits_uses_audited_service(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import web.routers.users as users_router

    fake_db = _FakeDB([{"telegram_user_id": 321, "username": "alice", "first_name": "Alice"}])
    app_client.app.dependency_overrides[users_router.get_db] = lambda: fake_db
    captured = {"kwargs": None}

    async def fake_update_limit_quota_with_audit(**kwargs):
        captured["kwargs"] = kwargs
        return (
            LimitQuotaDB(
                user_id=321,
                verification_level=VerificationLevel.EXTENDED,
                daily_limit=Decimal("10000000"),
                daily_used=Decimal("0"),
                daily_reset_at=next_daily_reset_at(datetime.now(timezone.utc)),
                monthly_limit=Decimal("50000000"),
                monthly_used=Decimal("0"),
                monthly_reset_at=next_monthly_reset_at(datetime.now(timezone.utc)),
            ),
            [object()],
        )

    monkeypatch.setattr(users_router, "update_limit_quota_with_audit", fake_update_limit_quota_with_audit)

    response = app_client.post(
        "/users/limits/321",
        auth=("admin", "password"),
        data={
            "verification_level": "extended",
            "daily_limit": "10000000",
            "monthly_limit": "50000000",
            "reason": "Escalated account",
        },
        follow_redirects=False,
    )

    app_client.app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "change(s) audited" in unquote_plus(response.headers["location"])
    assert captured["kwargs"] is not None
    assert captured["kwargs"]["user_id"] == 321
    assert captured["kwargs"]["verification_level"] == VerificationLevel.EXTENDED
    assert captured["kwargs"]["daily_limit"] == Decimal("10000000")
    assert captured["kwargs"]["monthly_limit"] == Decimal("50000000")
    assert captured["kwargs"]["reason"] == "Escalated account"


def test_broadcast_enqueues_traced_payloads(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import web.routers.users as users_router

    fake_db = _FakeDB(
        [
            {"telegram_user_id": 321, "username": "alice"},
            {"telegram_user_id": 654, "username": "bob"},
        ]
    )
    app_client.app.dependency_overrides[users_router.get_db] = lambda: fake_db
    queued_messages: list[tuple[str, dict]] = []

    async def fake_is_user_banned(user_id: int) -> bool:
        assert user_id in {321, 654}
        return False

    async def fake_publish_message(queue_name: str, message: str) -> None:
        queued_messages.append((queue_name, json.loads(message)))

    monkeypatch.setattr(users_router, "is_user_banned", fake_is_user_banned)
    monkeypatch.setattr(users_router, "publish_message", fake_publish_message)

    response = app_client.post(
        "/users/broadcast",
        auth=("admin", "password"),
        data={"message": "Latency probe"},
        follow_redirects=False,
    )

    app_client.app.dependency_overrides.clear()

    assert response.status_code == 303
    assert len(queued_messages) == 2
    for queue_name, payload in queued_messages:
        assert queue_name == settings.broadcast_queue_name
        assert payload["type"] == "broadcast"
        assert payload["text"] == "Latency probe"
        assert payload["_async_trace"]["producer"] == "web.users.broadcast"
        assert payload["_async_trace"]["queue_name"] == settings.broadcast_queue_name
        assert payload["_async_trace"]["event_name"] == "broadcast"
        assert payload["_async_trace"]["trace_id"] != ""
