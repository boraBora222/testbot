from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from fastapi.testclient import TestClient
import pytest

from shared import db
from shared.models import AuthSessionDB, OrderDB, OrderDraftDB, WebUserDB
from shared.types.enums import DraftSource, DraftStep, ExchangeType, OrderCreatedFrom, OrderStatus
from web.config import settings


VALID_ORDER_DICT = {
    "order_id": "ORD-20001",
    "user_id": 321,
    "username": "web-user@example.com",
    "exchange_type": ExchangeType.FIAT_TO_CRYPTO.value,
    "from_currency": "RUB",
    "to_currency": "USDT",
    "amount": Decimal("100000"),
    "network": "TRC20",
    "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "rate": Decimal("0.01081081"),
    "fee_percent": Decimal("0.5"),
    "fee_amount": Decimal("5.41"),
    "receive_amount": Decimal("1075.67"),
    "status": OrderStatus.NEW.value,
    "created_from": OrderCreatedFrom.MANUAL.value,
    "source_order_id": None,
    "source_draft_id": None,
    "is_demo": True,
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
}


def _authenticate_web_user(client: TestClient, *, linked_exchange_user_id: int | None) -> WebUserDB:
    user = WebUserDB(
        id="user_test",
        email="user@example.com",
        password_hash="hash",
        linked_exchange_user_id=linked_exchange_user_id,
    )
    session = AuthSessionDB(
        session_id="session_test",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db._web_users[user.email] = user
    db._auth_sessions[session.session_id] = session
    client.cookies.set(settings.auth_cookie_name, session.session_id)
    return user


def test_orders_api_requires_explicit_exchange_link(app_client: TestClient) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=None)

    response = app_client.get("/orders")

    assert response.status_code == 409
    assert response.json()["detail"] == "Current web account is not linked to an exchange user."


def test_list_orders_uses_group_filter(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_list_orders_for_user(
        user_id: int,
        page: int = 1,
        page_size: int = 10,
        status=None,
        statuses=None,
    ):
        assert user_id == 321
        assert page == 1
        assert page_size == 10
        assert status is None
        assert [item.value for item in statuses] == ["new", "waiting_payment", "processing"]
        return [VALID_ORDER_DICT], 1

    monkeypatch.setattr(db, "list_orders_for_user", fake_list_orders_for_user)

    response = app_client.get("/orders", params={"status": "active"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["status"] == "active"
    assert payload["items"][0]["order_id"] == "ORD-20001"
    assert payload["items"][0]["status_meta"]["is_terminal"] is False
    assert payload["items"][0]["can_repeat"] is False


def test_get_order_hides_foreign_orders(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-404"
        assert user_id == 321
        return None

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)

    response = app_client.get("/orders/ORD-404")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found."


def test_upsert_and_delete_current_order_draft(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    saved_draft = {"value": None}

    async def fake_get_current_order_draft(owner_channel: str, owner_id: str):
        assert owner_channel == "web"
        assert owner_id == "user_test"
        return None

    async def fake_create_or_replace_order_draft(draft: OrderDraftDB) -> OrderDraftDB:
        saved_draft["value"] = draft
        return draft

    async def fake_delete_order_draft(owner_channel: str, owner_id: str) -> bool:
        assert owner_channel == "web"
        assert owner_id == "user_test"
        return True

    monkeypatch.setattr(db, "get_current_order_draft", fake_get_current_order_draft)
    monkeypatch.setattr(db, "create_or_replace_order_draft", fake_create_or_replace_order_draft)
    monkeypatch.setattr(db, "delete_order_draft", fake_delete_order_draft)

    put_response = app_client.put(
        "/order-drafts/current",
        json={
            "source": "manual",
            "exchange_type": "fiat_to_crypto",
            "from_currency": "RUB",
            "to_currency": "USDT",
            "amount": "100000",
            "network": "TRC20",
            "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "use_whitelist": True,
            "current_step": "confirm",
        },
    )

    assert put_response.status_code == 200
    assert put_response.json()["owner_channel"] == "web"
    assert put_response.json()["owner_id"] == "user_test"
    assert saved_draft["value"] is not None
    assert saved_draft["value"].current_step == DraftStep.CONFIRM

    delete_response = app_client.delete("/order-drafts/current")

    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Draft deleted successfully."


def test_submit_current_order_draft_creates_order_and_removes_draft(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import web.routers.orders as orders_router

    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    submitted = {"payload": None}

    draft = OrderDraftDB(
        draft_id="draft_555",
        owner_channel="web",
        owner_id="user_test",
        source=DraftSource.MANUAL,
        exchange_type=ExchangeType.FIAT_TO_CRYPTO,
        from_currency="RUB",
        to_currency="USDT",
        amount=Decimal("100000"),
        network="TRC20",
        address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        use_whitelist=True,
        current_step=DraftStep.CONFIRM,
    )

    async def fake_get_current_order_draft(owner_channel: str, owner_id: str):
        assert owner_channel == "web"
        assert owner_id == "user_test"
        return draft.model_dump()

    async def fake_create_order_with_security_checks(**kwargs):
        submitted["payload"] = kwargs
        return (
            OrderDB(
                order_id="ORD-20099",
                user_id=321,
                username="user@example.com",
                exchange_type=ExchangeType.FIAT_TO_CRYPTO,
                from_currency="RUB",
                to_currency="USDT",
                amount=Decimal("100000"),
                network="TRC20",
                address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                address_source="whitelist",
                whitelist_address_id="wla_123",
                wallet_address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                wallet_network="TRC20",
                rate=Decimal("0.01081081"),
                fee_percent=Decimal("0.5"),
                fee_amount=Decimal("5.41"),
                receive_amount=Decimal("1075.67"),
                status=OrderStatus.NEW,
                created_from=OrderCreatedFrom.DRAFT_SUBMIT,
                source_draft_id="draft_555",
                is_demo=True,
            ),
            ["This order exceeds the configured daily or monthly limit. It was created and flagged for manager review."],
        )

    async def fake_delete_order_draft(owner_channel: str, owner_id: str) -> bool:
        assert owner_channel == "web"
        assert owner_id == "user_test"
        return True

    monkeypatch.setattr(db, "get_current_order_draft", fake_get_current_order_draft)
    monkeypatch.setattr(orders_router, "create_order_with_security_checks", fake_create_order_with_security_checks)
    monkeypatch.setattr(db, "delete_order_draft", fake_delete_order_draft)

    response = app_client.post("/order-drafts/current/submit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] == "ORD-20099"
    assert payload["created_from"] == "draft_submit"
    assert payload["source_draft_id"] == "draft_555"
    assert payload["address_source"] == "whitelist"
    assert payload["whitelist_address_id"] == "wla_123"
    assert payload["warnings"] == [
        "This order exceeds the configured daily or monthly limit. It was created and flagged for manager review."
    ]
    assert submitted["payload"] is not None
    assert submitted["payload"]["user_id"] == 321


def test_submit_current_order_draft_rejects_unapproved_whitelist_address(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import web.routers.orders as orders_router
    from shared.services.security_settings import WhitelistApprovalRequiredError

    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    draft = OrderDraftDB(
        draft_id="draft_556",
        owner_channel="web",
        owner_id="user_test",
        source=DraftSource.MANUAL,
        exchange_type=ExchangeType.FIAT_TO_CRYPTO,
        from_currency="RUB",
        to_currency="USDT",
        amount=Decimal("100000"),
        network="TRC20",
        address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        current_step=DraftStep.CONFIRM,
    )

    async def fake_get_current_order_draft(owner_channel: str, owner_id: str):
        return draft.model_dump()

    async def fake_create_order_with_security_checks(**kwargs):
        raise WhitelistApprovalRequiredError(
            "This wallet address is not in the active whitelist. Add it to the whitelist and wait for moderation before creating an order."
        )

    monkeypatch.setattr(db, "get_current_order_draft", fake_get_current_order_draft)
    monkeypatch.setattr(orders_router, "create_order_with_security_checks", fake_create_order_with_security_checks)

    response = app_client.post("/order-drafts/current/submit")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This wallet address is not in the active whitelist. Add it to the whitelist and wait for moderation before creating an order."
    )
