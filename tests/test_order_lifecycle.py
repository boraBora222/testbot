from decimal import Decimal

import pytest

from shared.security_settings import ensure_whitelist_entry_can_be_created, find_matching_whitelist_entry
from shared.services.order_lifecycle import (
    build_order_draft,
    build_order_from_payload,
    build_order_state_from_draft,
    build_repeat_seed,
    build_status_meta,
    get_status_filter_values,
)
from shared.types.enums import AddressSource, DraftSource, DraftStep, ExchangeType, OrderCreatedFrom, OrderListFilter, OrderStatus


VALID_ORDER_PAYLOAD = {
    "exchange_type": ExchangeType.FIAT_TO_CRYPTO.value,
    "from_currency": "RUB",
    "to_currency": "USDT",
    "amount": "100000",
    "network": "TRC20",
    "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "use_whitelist": True,
}


def test_active_filter_expands_to_product_status_group() -> None:
    assert get_status_filter_values(OrderListFilter.ACTIVE) == (
        OrderStatus.NEW,
        OrderStatus.WAITING_PAYMENT,
        OrderStatus.PROCESSING,
    )


def test_status_meta_for_completed_is_terminal() -> None:
    status_meta = build_status_meta(OrderStatus.COMPLETED)

    assert status_meta.is_terminal is True
    assert status_meta.eta_text is None
    assert "заверш" in status_meta.title.lower()


def test_repeat_seed_copies_only_form_fields() -> None:
    order = build_order_from_payload(
        order_id="ORD-10001",
        user_id=123,
        username="alice",
        payload=VALID_ORDER_PAYLOAD,
        is_demo=True,
        created_from=OrderCreatedFrom.REPEAT,
        source_order_id="ORD-00099",
    )
    order.status = OrderStatus.COMPLETED

    repeat_seed = build_repeat_seed(order.model_dump())

    assert repeat_seed == {
        "exchange_type": ExchangeType.FIAT_TO_CRYPTO.value,
        "from_currency": "RUB",
        "to_currency": "USDT",
        "amount": "100000",
        "network": "TRC20",
        "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "source": DraftSource.REPEAT.value,
        "source_order_id": "ORD-10001",
        "current_step": DraftStep.CONFIRM.value,
    }


def test_build_order_draft_and_resume_state_roundtrip() -> None:
    draft = build_order_draft(
        owner_channel="telegram",
        owner_id="123",
        payload=VALID_ORDER_PAYLOAD,
        source=DraftSource.MANUAL,
        current_step=DraftStep.CONFIRM,
        draft_id="draft_001",
    )

    resumed_state = build_order_state_from_draft(draft)

    assert resumed_state["draft_id"] == "draft_001"
    assert resumed_state["draft_source"] == DraftSource.MANUAL.value
    assert resumed_state["exchange_type"] == ExchangeType.FIAT_TO_CRYPTO.value
    assert resumed_state["amount"] == "100000"
    assert resumed_state["resumed_from_draft"] is True


def test_build_order_from_payload_marks_draft_submit_metadata() -> None:
    order = build_order_from_payload(
        order_id="ORD-10002",
        user_id=456,
        username="bob",
        payload=VALID_ORDER_PAYLOAD,
        is_demo=False,
        created_from=OrderCreatedFrom.DRAFT_SUBMIT,
        source_order_id="ORD-00077",
        source_draft_id="draft_123",
    )

    assert order.created_from == OrderCreatedFrom.DRAFT_SUBMIT
    assert order.source_order_id == "ORD-00077"
    assert order.source_draft_id == "draft_123"
    assert order.status == OrderStatus.NEW
    assert order.amount == Decimal("100000")


def test_build_order_from_payload_sets_wallet_provenance_defaults() -> None:
    order = build_order_from_payload(
        order_id="ORD-10003",
        user_id=789,
        username="carol",
        payload=VALID_ORDER_PAYLOAD,
        is_demo=True,
        created_from=OrderCreatedFrom.MANUAL,
    )

    assert order.address_source == AddressSource.MANUAL
    assert order.whitelist_address_id is None
    assert order.wallet_address == VALID_ORDER_PAYLOAD["address"]
    assert order.wallet_network == VALID_ORDER_PAYLOAD["network"]


def test_build_order_from_payload_requires_whitelist_reference() -> None:
    with pytest.raises(ValueError, match="whitelist_address_id is required"):
        build_order_from_payload(
            order_id="ORD-10004",
            user_id=789,
            username="dave",
            payload={
                **VALID_ORDER_PAYLOAD,
                "address_source": AddressSource.WHITELIST.value,
            },
            is_demo=True,
            created_from=OrderCreatedFrom.MANUAL,
        )


def test_whitelist_validation_enforces_caps_and_rejected_resubmission() -> None:
    existing_entries = [
        {
            "network": "TRC-20",
            "address": f"T{'A' * 33}",
            "address_normalized": f"T{'A' * 33}",
            "status": "pending",
        },
        {
            "network": "ERC-20",
            "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "address_normalized": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "status": "active",
        },
        {
            "network": "BEP-20",
            "address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "address_normalized": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "status": "active",
        },
        {
            "network": "TRC-20",
            "address": f"T{'B' * 33}",
            "address_normalized": f"T{'B' * 33}",
            "status": "pending",
        },
        {
            "network": "ERC-20",
            "address": "0xcccccccccccccccccccccccccccccccccccccccc",
            "address_normalized": "0xcccccccccccccccccccccccccccccccccccccccc",
            "status": "active",
        },
    ]

    with pytest.raises(ValueError, match="at most 5 addresses"):
        ensure_whitelist_entry_can_be_created(
            existing_entries,
            network="TRC20",
            address=f"T{'C' * 33}",
        )

    with pytest.raises(ValueError, match="cannot be submitted again"):
        ensure_whitelist_entry_can_be_created(
            [
                {
                    "network": "ERC-20",
                    "address": "0xdddddddddddddddddddddddddddddddddddddddd",
                    "address_normalized": "0xdddddddddddddddddddddddddddddddddddddddd",
                    "status": "rejected",
                }
            ],
            network="ERC20",
            address="0xDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
        )


def test_find_matching_whitelist_entry_matches_network_aliases_and_normalized_address() -> None:
    match = find_matching_whitelist_entry(
        [
            {
                "id": "wla_1",
                "network": "ERC-20",
                "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "address_normalized": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "status": "active",
            }
        ],
        network="ERC20",
        address="0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )

    assert match is not None
    assert match["id"] == "wla_1"
