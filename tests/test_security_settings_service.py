from datetime import datetime, timezone
from decimal import Decimal

import pytest

from shared.models import LimitQuotaDB
from shared.security_settings import next_daily_reset_at, next_monthly_reset_at
from shared.services.security_settings import (
    WhitelistApprovalRequiredError,
    build_default_whitelist_label,
    create_pending_whitelist_entry,
    create_order_with_security_checks,
    update_limit_quota_with_audit,
)
from shared.types.enums import OrderCreatedFrom, VerificationLevel


@pytest.mark.anyio
async def test_create_order_with_security_checks_binds_active_whitelist_and_returns_limit_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import db

    captured = {"order": None}

    async def fake_find_active_whitelist_address(user_id: int, network: str, address: str):
        assert user_id == 321
        assert network == "TRC20"
        assert address == "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        return {
            "id": "wla_active",
            "user_id": 321,
            "network": "TRC-20",
            "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "status": "active",
        }

    async def fake_get_next_order_id() -> str:
        return "ORD-30001"

    async def fake_create_order(order):
        captured["order"] = order
        return "mongo-order-id"

    async def fake_increment_limit_quota_usage(user_id: int, amount: Decimal):
        assert user_id == 321
        assert amount == Decimal("100000")
        return LimitQuotaDB(
            user_id=321,
            verification_level=VerificationLevel.EXTENDED,
            daily_limit=Decimal("90000"),
            daily_used=Decimal("100000"),
            daily_reset_at=next_daily_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
            monthly_limit=Decimal("50000000"),
            monthly_used=Decimal("100000"),
            monthly_reset_at=next_monthly_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
        )

    monkeypatch.setattr(db, "find_active_whitelist_address", fake_find_active_whitelist_address)
    monkeypatch.setattr(db, "get_next_order_id", fake_get_next_order_id)
    monkeypatch.setattr(db, "create_order", fake_create_order)
    monkeypatch.setattr(db, "increment_limit_quota_usage", fake_increment_limit_quota_usage)

    order, warnings = await create_order_with_security_checks(
        user_id=321,
        username="alice",
        payload={
            "exchange_type": "fiat_to_crypto",
            "from_currency": "RUB",
            "to_currency": "USDT",
            "amount": "100000",
            "network": "TRC20",
            "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        },
        is_demo=True,
        created_from=OrderCreatedFrom.MANUAL,
    )

    assert order.order_id == "ORD-30001"
    assert order.address_source == "whitelist"
    assert order.whitelist_address_id == "wla_active"
    assert captured["order"] is not None
    assert warnings == [
        "This order exceeds the configured daily or monthly limit. It was created and flagged for manager review."
    ]


@pytest.mark.anyio
async def test_create_order_with_security_checks_rejects_non_whitelisted_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import db

    async def fake_find_active_whitelist_address(user_id: int, network: str, address: str):
        return None

    monkeypatch.setattr(db, "find_active_whitelist_address", fake_find_active_whitelist_address)

    with pytest.raises(WhitelistApprovalRequiredError, match="active whitelist"):
        await create_order_with_security_checks(
            user_id=321,
            username="alice",
            payload={
                "exchange_type": "fiat_to_crypto",
                "from_currency": "RUB",
                "to_currency": "USDT",
                "amount": "100000",
                "network": "TRC20",
                "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            },
            is_demo=True,
            created_from=OrderCreatedFrom.MANUAL,
        )


@pytest.mark.anyio
async def test_update_limit_quota_with_audit_writes_history_for_changed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import db

    captured = {"quota": None, "history": None}

    existing_quota = LimitQuotaDB(
        user_id=321,
        verification_level=VerificationLevel.BASIC,
        daily_limit=Decimal("1000000"),
        daily_used=Decimal("100"),
        daily_reset_at=next_daily_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
        monthly_limit=Decimal("5000000"),
        monthly_used=Decimal("1000"),
        monthly_reset_at=next_monthly_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
    )

    async def fake_get_limit_quota(user_id: int):
        assert user_id == 321
        return existing_quota.model_dump()

    async def fake_upsert_limit_quota(quota: LimitQuotaDB):
        captured["quota"] = quota
        return quota

    async def fake_insert_limit_quota_history(entries):
        captured["history"] = entries

    monkeypatch.setattr(db, "get_limit_quota", fake_get_limit_quota)
    monkeypatch.setattr(db, "upsert_limit_quota", fake_upsert_limit_quota)
    monkeypatch.setattr(db, "insert_limit_quota_history", fake_insert_limit_quota_history)

    saved_quota, history_rows = await update_limit_quota_with_audit(
        user_id=321,
        verification_level=VerificationLevel.EXTENDED,
        daily_limit=Decimal("10000000"),
        monthly_limit=Decimal("50000000"),
        reason="Manual review approved",
        changed_by="admin",
    )

    assert saved_quota.verification_level == VerificationLevel.EXTENDED
    assert saved_quota.daily_limit == Decimal("10000000")
    assert saved_quota.monthly_limit == Decimal("50000000")
    assert captured["quota"] is not None
    assert captured["history"] is not None
    assert [row.field for row in history_rows] == ["verification_level", "daily_limit", "monthly_limit"]
    assert history_rows[0].old_value == "basic"
    assert history_rows[0].new_value == "extended"


@pytest.mark.anyio
async def test_create_pending_whitelist_entry_generates_default_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import db

    captured = {"entry": None}

    async def fake_list_whitelist_addresses_for_user(user_id: int):
        assert user_id == 321
        return []

    async def fake_create_whitelist_address(entry):
        captured["entry"] = entry
        return entry

    monkeypatch.setattr(db, "list_whitelist_addresses_for_user", fake_list_whitelist_addresses_for_user)
    monkeypatch.setattr(db, "create_whitelist_address", fake_create_whitelist_address)

    entry = await create_pending_whitelist_entry(
        user_id=321,
        network="TRC20",
        address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )

    assert entry.network == "TRC-20"
    assert entry.label == build_default_whitelist_label("TRC-20", "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert captured["entry"] is not None


@pytest.mark.anyio
async def test_create_pending_whitelist_entry_preserves_explicit_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import db

    async def fake_list_whitelist_addresses_for_user(user_id: int):
        assert user_id == 321
        return []

    async def fake_create_whitelist_address(entry):
        return entry

    monkeypatch.setattr(db, "list_whitelist_addresses_for_user", fake_list_whitelist_addresses_for_user)
    monkeypatch.setattr(db, "create_whitelist_address", fake_create_whitelist_address)

    entry = await create_pending_whitelist_entry(
        user_id=321,
        network="ERC20",
        address="0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        label="Treasury",
    )

    assert entry.label == "Treasury"
