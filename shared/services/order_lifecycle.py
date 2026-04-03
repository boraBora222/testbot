from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from shared.exchange_logic import (
    calculate_order_preview,
    get_available_from_currencies,
    get_available_to_currencies,
    get_network_options,
    validate_address,
    validate_amount,
)
from shared.config import settings
from shared.models import OrderDB, OrderDraftDB, OrderTimelineStep, StatusMeta
from shared.types.enums import (
    AddressSource,
    DraftSource,
    DraftStep,
    ExchangeType,
    OrderCreatedFrom,
    OrderListFilter,
    OrderStatus,
)

logger = logging.getLogger(__name__)

DRAFT_SCHEMA_VERSION = 1
ACTIVE_ORDER_STATUSES = (
    OrderStatus.NEW,
    OrderStatus.WAITING_PAYMENT,
    OrderStatus.PROCESSING,
)
REPEATABLE_ORDER_STATUSES = (
    OrderStatus.COMPLETED,
    OrderStatus.CANCELLED,
)
ORDER_FILTER_STATUSES: dict[OrderListFilter, tuple[OrderStatus, ...]] = {
    OrderListFilter.ALL: (),
    OrderListFilter.ACTIVE: ACTIVE_ORDER_STATUSES,
    OrderListFilter.NEW: (OrderStatus.NEW,),
    OrderListFilter.WAITING_PAYMENT: (OrderStatus.WAITING_PAYMENT,),
    OrderListFilter.PROCESSING: (OrderStatus.PROCESSING,),
    OrderListFilter.COMPLETED: (OrderStatus.COMPLETED,),
    OrderListFilter.CANCELLED: (OrderStatus.CANCELLED,),
}
STATUS_META_TEMPLATES: dict[OrderStatus, StatusMeta] = {
    OrderStatus.NEW: StatusMeta(
        title="Новая заявка",
        reason="Заявка получена и ожидает первичной обработки.",
        eta_text="Обычно до 15 минут.",
        next_step="Менеджер проверит параметры и свяжется с вами.",
        is_terminal=False,
    ),
    OrderStatus.WAITING_PAYMENT: StatusMeta(
        title="Ожидаем оплату",
        reason="Ожидаем поступление или подтверждение оплаты.",
        eta_text="Зависит от платёжного канала и сети.",
        next_step="После подтверждения платежа заявка перейдёт в обработку.",
        is_terminal=False,
    ),
    OrderStatus.PROCESSING: StatusMeta(
        title="В работе",
        reason="Операция выполняется.",
        eta_text="Обычно 5-15 минут.",
        next_step="Мы завершим обмен и обновим статус заявки.",
        is_terminal=False,
    ),
    OrderStatus.COMPLETED: StatusMeta(
        title="Сделка завершена",
        reason="Заявка успешно обработана.",
        eta_text=None,
        next_step=None,
        is_terminal=True,
    ),
    OrderStatus.CANCELLED: StatusMeta(
        title="Сделка отменена",
        reason="Заявка отменена и больше не обрабатывается.",
        eta_text=None,
        next_step="Вы можете повторить заявку с актуальными параметрами.",
        is_terminal=True,
    ),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_order_status(status: OrderStatus | str) -> OrderStatus:
    return status if isinstance(status, OrderStatus) else OrderStatus(status)


def normalize_order_filter(order_filter: OrderListFilter | str) -> OrderListFilter:
    return order_filter if isinstance(order_filter, OrderListFilter) else OrderListFilter(order_filter)


def get_status_filter_values(order_filter: OrderListFilter | str) -> tuple[OrderStatus, ...]:
    normalized_filter = normalize_order_filter(order_filter)
    return ORDER_FILTER_STATUSES[normalized_filter]


def build_status_meta(status: OrderStatus | str) -> StatusMeta:
    normalized_status = normalize_order_status(status)
    template = STATUS_META_TEMPLATES[normalized_status]
    return StatusMeta(**template.model_dump())


def can_repeat_order(order_or_status: Mapping[str, Any] | OrderStatus | str) -> bool:
    if isinstance(order_or_status, Mapping):
        status = normalize_order_status(order_or_status["status"])
        return status in REPEATABLE_ORDER_STATUSES
    return normalize_order_status(order_or_status) in REPEATABLE_ORDER_STATUSES


def build_repeat_seed(order: Mapping[str, Any]) -> dict[str, Any]:
    if not can_repeat_order(order):
        logger.error("Repeat requested for non-repeatable order. order_id=%s status=%s", order.get("order_id"), order.get("status"))
        raise ValueError("Repeat is available only for completed or cancelled orders.")

    return {
        "exchange_type": order["exchange_type"],
        "from_currency": order["from_currency"],
        "to_currency": order["to_currency"],
        "amount": str(order["amount"]),
        "network": order["network"],
        "address": order["address"],
        "source": DraftSource.REPEAT.value,
        "source_order_id": order["order_id"],
        "current_step": DraftStep.CONFIRM.value,
    }


def _require_payload_field(payload: Mapping[str, Any], field_name: str) -> Any:
    if field_name not in payload or payload[field_name] is None:
        raise ValueError(f"Missing required order field: {field_name}")
    return payload[field_name]


def validate_order_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    exchange_type = ExchangeType(_require_payload_field(payload, "exchange_type"))
    from_currency = str(_require_payload_field(payload, "from_currency")).strip().upper()
    to_currency = str(_require_payload_field(payload, "to_currency")).strip().upper()
    network = str(_require_payload_field(payload, "network")).strip().upper()
    address = str(_require_payload_field(payload, "address")).strip()
    whitelist_address_id = payload.get("whitelist_address_id")

    if from_currency not in get_available_from_currencies(exchange_type.value):
        raise ValueError(f"Unsupported source currency for exchange type: {from_currency}")

    if to_currency not in get_available_to_currencies(exchange_type.value, from_currency):
        raise ValueError(f"Unsupported destination currency for exchange type: {to_currency}")

    if from_currency == to_currency:
        raise ValueError("Source and destination currencies must differ.")

    allowed_networks = {option["code"] for option in get_network_options(exchange_type.value, from_currency, to_currency)}
    if network not in allowed_networks:
        raise ValueError(f"Unsupported network for selected currencies: {network}")

    is_valid_amount, amount_error, amount = validate_amount(str(_require_payload_field(payload, "amount")), from_currency)
    if not is_valid_amount or amount is None:
        raise ValueError(amount_error)

    is_valid_address, address_error = validate_address(
        exchange_type.value,
        from_currency,
        to_currency,
        network,
        address,
    )
    if not is_valid_address:
        raise ValueError(address_error)

    normalized_payload = {
        "exchange_type": exchange_type,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "amount": amount,
        "network": network,
        "address": address,
    }
    if payload.get("address_source") is not None:
        address_source = AddressSource(payload["address_source"])
    elif whitelist_address_id is not None:
        address_source = AddressSource.WHITELIST
    else:
        address_source = AddressSource.MANUAL

    if whitelist_address_id is not None:
        whitelist_address_id = str(whitelist_address_id).strip()
        if not whitelist_address_id:
            raise ValueError("whitelist_address_id cannot be empty.")

    if address_source == AddressSource.WHITELIST and whitelist_address_id is None:
        raise ValueError("whitelist_address_id is required when address_source is whitelist.")
    if address_source == AddressSource.MANUAL and whitelist_address_id is not None:
        raise ValueError("whitelist_address_id must be empty when address_source is manual.")

    normalized_payload["address_source"] = address_source
    normalized_payload["whitelist_address_id"] = whitelist_address_id
    if "use_whitelist" in payload and payload["use_whitelist"] is not None:
        normalized_payload["use_whitelist"] = bool(payload["use_whitelist"])
    return normalized_payload


def build_order_from_payload(
    *,
    order_id: str,
    user_id: int,
    username: str | None,
    payload: Mapping[str, Any],
    is_demo: bool,
    created_from: OrderCreatedFrom | str,
    source_order_id: str | None = None,
    source_draft_id: str | None = None,
) -> OrderDB:
    normalized_payload = validate_order_payload(payload)
    preview = calculate_order_preview(
        from_currency=normalized_payload["from_currency"],
        to_currency=normalized_payload["to_currency"],
        amount=normalized_payload["amount"],
    )
    return OrderDB(
        order_id=order_id,
        user_id=user_id,
        username=username,
        exchange_type=normalized_payload["exchange_type"],
        from_currency=normalized_payload["from_currency"],
        to_currency=normalized_payload["to_currency"],
        amount=normalized_payload["amount"],
        network=normalized_payload["network"],
        address=normalized_payload["address"],
        address_source=normalized_payload["address_source"],
        whitelist_address_id=normalized_payload["whitelist_address_id"],
        wallet_address=normalized_payload["address"],
        wallet_network=normalized_payload["network"],
        rate=preview["rate"],
        fee_percent=settings.default_fee_percent,
        fee_amount=preview["fee_amount"],
        receive_amount=preview["receive_amount"],
        created_from=OrderCreatedFrom(created_from),
        source_order_id=source_order_id,
        source_draft_id=source_draft_id,
        is_demo=is_demo,
    )


def build_order_draft(
    *,
    owner_channel: str,
    owner_id: str,
    payload: Mapping[str, Any],
    source: DraftSource | str,
    current_step: DraftStep | str,
    source_order_id: str | None = None,
    draft_id: str | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> OrderDraftDB:
    if owner_channel not in {"telegram", "web"}:
        raise ValueError(f"Unsupported owner channel: {owner_channel}")
    if not owner_id.strip():
        raise ValueError("Draft owner_id is required.")

    normalized_step = DraftStep(current_step)
    normalized_source = DraftSource(source)
    now = _utc_now()

    exchange_type: ExchangeType | None = None
    if payload.get("exchange_type") is not None:
        exchange_type = ExchangeType(payload["exchange_type"])

    from_currency = None
    if payload.get("from_currency") is not None:
        from_currency = str(payload["from_currency"]).strip().upper()

    to_currency = None
    if payload.get("to_currency") is not None:
        to_currency = str(payload["to_currency"]).strip().upper()

    network = None
    if payload.get("network") is not None:
        network = str(payload["network"]).strip().upper()

    address = None
    if payload.get("address") is not None:
        address = str(payload["address"]).strip()

    amount: Decimal | None = None
    if payload.get("amount") is not None:
        if from_currency is None:
            raise ValueError("from_currency is required when amount is provided for a draft.")
        is_valid_amount, amount_error, normalized_amount = validate_amount(str(payload["amount"]), from_currency)
        if not is_valid_amount or normalized_amount is None:
            raise ValueError(amount_error)
        amount = normalized_amount

    if normalized_step == DraftStep.CONFIRM:
        normalized_order_payload = validate_order_payload(payload)
        exchange_type = normalized_order_payload["exchange_type"]
        from_currency = normalized_order_payload["from_currency"]
        to_currency = normalized_order_payload["to_currency"]
        amount = normalized_order_payload["amount"]
        network = normalized_order_payload["network"]
        address = normalized_order_payload["address"]

    return OrderDraftDB(
        draft_id=draft_id or f"draft_{uuid.uuid4().hex}",
        owner_channel=owner_channel,
        owner_id=owner_id.strip(),
        source=normalized_source,
        source_order_id=source_order_id,
        exchange_type=exchange_type,
        from_currency=from_currency,
        to_currency=to_currency,
        amount=amount,
        network=network,
        address=address,
        use_whitelist=payload.get("use_whitelist"),
        current_step=normalized_step,
        schema_version=DRAFT_SCHEMA_VERSION,
        created_at=created_at or now,
        updated_at=now,
        expires_at=expires_at,
    )


def build_order_state_from_draft(draft: OrderDraftDB | Mapping[str, Any]) -> dict[str, Any]:
    source_draft = draft if isinstance(draft, OrderDraftDB) else OrderDraftDB(**draft)
    if source_draft.schema_version != DRAFT_SCHEMA_VERSION:
        logger.error(
            "Draft schema version mismatch. draft_id=%s expected=%s actual=%s",
            source_draft.draft_id,
            DRAFT_SCHEMA_VERSION,
            source_draft.schema_version,
        )
        raise ValueError("Draft schema is outdated.")

    required_fields = (
        "exchange_type",
        "from_currency",
        "to_currency",
        "amount",
        "network",
        "address",
    )
    for field_name in required_fields:
        if getattr(source_draft, field_name) is None:
            raise ValueError(f"Draft cannot be resumed because field {field_name} is missing.")

    state_payload = {
        "exchange_type": source_draft.exchange_type.value,
        "from_currency": source_draft.from_currency,
        "to_currency": source_draft.to_currency,
        "amount": str(source_draft.amount),
        "network": source_draft.network,
        "address": source_draft.address,
        "draft_id": source_draft.draft_id,
        "draft_source": source_draft.source.value,
        "current_step": source_draft.current_step.value,
        "resumed_from_draft": True,
    }
    if source_draft.source_order_id is not None:
        state_payload["source_order_id"] = source_draft.source_order_id
    if source_draft.use_whitelist is not None:
        state_payload["use_whitelist"] = source_draft.use_whitelist
    return state_payload


def build_order_timeline(order: Mapping[str, Any]) -> list[OrderTimelineStep]:
    status = normalize_order_status(order["status"])
    created_at = order["created_at"]
    updated_at = order["updated_at"]

    timeline_statuses: dict[OrderStatus, list[tuple[str, str, str, datetime | None]]] = {
        OrderStatus.NEW: [
            ("created", "Заявка создана", "active", created_at),
            ("waiting_payment", "Ожидание оплаты", "pending", None),
            ("processing", "Обработка", "pending", None),
            ("terminal", "Сделка завершена", "pending", None),
        ],
        OrderStatus.WAITING_PAYMENT: [
            ("created", "Заявка создана", "completed", created_at),
            ("waiting_payment", "Ожидание оплаты", "active", updated_at),
            ("processing", "Обработка", "pending", None),
            ("terminal", "Сделка завершена", "pending", None),
        ],
        OrderStatus.PROCESSING: [
            ("created", "Заявка создана", "completed", created_at),
            ("waiting_payment", "Ожидание оплаты", "completed", updated_at),
            ("processing", "Обработка", "active", updated_at),
            ("terminal", "Сделка завершена", "pending", None),
        ],
        OrderStatus.COMPLETED: [
            ("created", "Заявка создана", "completed", created_at),
            ("waiting_payment", "Ожидание оплаты", "completed", updated_at),
            ("processing", "Обработка", "completed", updated_at),
            ("terminal", "Сделка завершена", "completed", updated_at),
        ],
        OrderStatus.CANCELLED: [
            ("created", "Заявка создана", "completed", created_at),
            ("waiting_payment", "Ожидание оплаты", "pending", None),
            ("processing", "Обработка", "pending", None),
            ("terminal", "Сделка отменена", "active", updated_at),
        ],
    }

    return [
        OrderTimelineStep(key=key, label=label, status=step_status, timestamp=timestamp)
        for key, label, step_status, timestamp in timeline_statuses[status]
    ]


def build_available_actions(order: Mapping[str, Any]) -> list[str]:
    actions: list[str] = []
    if can_repeat_order(order):
        actions.append("repeat")
    return actions


def build_order_list_item(order: Mapping[str, Any]) -> dict[str, Any]:
    serialized_order = dict(order)
    serialized_order["status_meta"] = build_status_meta(serialized_order["status"]).model_dump()
    serialized_order["can_repeat"] = can_repeat_order(serialized_order)
    return serialized_order


def build_order_detail_payload(order: Mapping[str, Any]) -> dict[str, Any]:
    serialized_order = build_order_list_item(order)
    serialized_order["timeline"] = [step.model_dump() for step in build_order_timeline(order)]
    serialized_order["available_actions"] = build_available_actions(order)
    return serialized_order
