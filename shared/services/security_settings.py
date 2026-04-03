from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Mapping

from shared import db
from shared.models import LimitQuotaDB, LimitQuotaHistoryDB, OrderDB, WhitelistAddressDB
from shared.security_settings import (
    LIMIT_WARNING_MESSAGE,
    WHITELIST_APPROVAL_REQUIRED_MESSAGE,
    ensure_whitelist_entry_can_be_created,
    next_daily_reset_at,
    next_monthly_reset_at,
    utc_now,
)
from shared.services.order_lifecycle import build_order_from_payload, validate_order_payload
from shared.types.enums import AddressSource, OrderCreatedFrom, VerificationLevel

logger = logging.getLogger(__name__)


class WhitelistApprovalRequiredError(ValueError):
    """Raised when order creation is attempted without an active whitelist match."""


class LimitQuotaNotConfiguredError(RuntimeError):
    """Raised when quota tracking is required but the user has no configured quota."""


def _serialize_audit_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    return value


def build_default_whitelist_label(network: str, address: str) -> str:
    tail = address.strip()[-6:] if address.strip() else "wallet"
    return f"Wallet {network} {tail}"


async def create_pending_whitelist_entry(
    *,
    user_id: int,
    network: str,
    address: str,
    label: str | None = None,
) -> WhitelistAddressDB:
    existing_entries = await db.list_whitelist_addresses_for_user(user_id)
    canonical_network, _ = ensure_whitelist_entry_can_be_created(
        existing_entries,
        network=network,
        address=address,
    )
    entry = WhitelistAddressDB(
        user_id=user_id,
        network=canonical_network,
        address=address,
        label=label if label is not None else build_default_whitelist_label(canonical_network, address),
    )
    return await db.create_whitelist_address(entry)


async def resolve_order_whitelist_payload(user_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized_payload = validate_order_payload(payload)
    whitelist_entry = await db.find_active_whitelist_address(
        user_id,
        normalized_payload["network"],
        normalized_payload["address"],
    )
    if whitelist_entry is None:
        raise WhitelistApprovalRequiredError(WHITELIST_APPROVAL_REQUIRED_MESSAGE)

    requested_whitelist_id = normalized_payload.get("whitelist_address_id")
    if requested_whitelist_id is not None and requested_whitelist_id != whitelist_entry["id"]:
        raise WhitelistApprovalRequiredError(WHITELIST_APPROVAL_REQUIRED_MESSAGE)

    normalized_payload["address"] = whitelist_entry["address"]
    normalized_payload["address_source"] = AddressSource.WHITELIST
    normalized_payload["whitelist_address_id"] = whitelist_entry["id"]
    return normalized_payload


async def create_order_with_security_checks(
    *,
    user_id: int,
    username: str | None,
    payload: Mapping[str, Any],
    is_demo: bool,
    created_from: OrderCreatedFrom | str,
    source_order_id: str | None = None,
    source_draft_id: str | None = None,
) -> tuple[OrderDB, list[str]]:
    secured_payload = await resolve_order_whitelist_payload(user_id, payload)
    order_id = await db.get_next_order_id()
    order = build_order_from_payload(
        order_id=order_id,
        user_id=user_id,
        username=username,
        payload=secured_payload,
        is_demo=is_demo,
        created_from=created_from,
        source_order_id=source_order_id,
        source_draft_id=source_draft_id,
    )

    await db.create_order(order)
    try:
        quota = await db.increment_limit_quota_usage(user_id, order.amount)
        if quota is None:
            raise LimitQuotaNotConfiguredError("Limit quota is not configured for current exchange user.")
    except Exception:
        try:
            deleted = await db.delete_order_by_order_id(order.order_id)
        except Exception:  # pragma: no cover - defensive logging path
            logger.exception("Failed to rollback order after quota update error. order_id=%s", order.order_id)
        else:
            if not deleted:
                logger.error("Order rollback did not remove the order after quota update error. order_id=%s", order.order_id)
        raise

    warnings: list[str] = []
    if quota.daily_used > quota.daily_limit or quota.monthly_used > quota.monthly_limit:
        warnings.append(LIMIT_WARNING_MESSAGE)
    return order, warnings


async def update_limit_quota_with_audit(
    *,
    user_id: int,
    verification_level: VerificationLevel | str,
    daily_limit: Decimal,
    monthly_limit: Decimal,
    reason: str,
    changed_by: str,
) -> tuple[LimitQuotaDB, list[LimitQuotaHistoryDB]]:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("Reason is required.")

    normalized_actor = changed_by.strip()
    if not normalized_actor:
        raise ValueError("Actor is required.")

    normalized_level = VerificationLevel(verification_level)
    now = utc_now()
    existing_payload = await db.get_limit_quota(user_id)
    existing = LimitQuotaDB(**existing_payload) if existing_payload is not None else None

    if existing is None:
        updated_quota = LimitQuotaDB(
            user_id=user_id,
            verification_level=normalized_level,
            daily_limit=daily_limit,
            daily_used=Decimal("0"),
            daily_reset_at=next_daily_reset_at(now),
            monthly_limit=monthly_limit,
            monthly_used=Decimal("0"),
            monthly_reset_at=next_monthly_reset_at(now),
            updated_at=now,
        )
    else:
        updated_quota = existing.model_copy(
            update={
                "verification_level": normalized_level,
                "daily_limit": daily_limit,
                "monthly_limit": monthly_limit,
                "updated_at": now,
            }
        )

    tracked_fields = ("verification_level", "daily_limit", "monthly_limit")
    history_rows: list[LimitQuotaHistoryDB] = []
    for field_name in tracked_fields:
        previous_value = getattr(existing, field_name, None) if existing is not None else None
        next_value = getattr(updated_quota, field_name)
        if previous_value == next_value:
            continue
        history_rows.append(
            LimitQuotaHistoryDB(
                user_id=user_id,
                changed_by=normalized_actor,
                field=field_name,
                old_value=_serialize_audit_value(previous_value),
                new_value=_serialize_audit_value(next_value),
                reason=normalized_reason,
                created_at=now,
            )
        )

    if existing is not None and not history_rows:
        return existing, []

    saved_quota = await db.upsert_limit_quota(updated_quota)
    await db.insert_limit_quota_history(history_rows)
    return saved_quota, history_rows
