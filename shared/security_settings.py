from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from shared.types.enums import WhitelistAddressStatus

SUPPORTED_WHITELIST_NETWORKS = ("TRC-20", "ERC-20", "BEP-20")
NOTIFICATION_EVENT_KEYS = (
    "order_created",
    "order_status_changed",
    "support_reply",
    "limit_warning",
)
MAX_PENDING_OR_ACTIVE_WHITELIST_ADDRESSES = 5
WHITELIST_APPROVAL_REQUIRED_MESSAGE = (
    "This wallet address is not in the active whitelist. Add it to the whitelist and wait for moderation before creating an order."
)
LIMIT_WARNING_MESSAGE = (
    "This order exceeds the configured daily or monthly limit. It was created and flagged for manager review."
)

_WHITELIST_NETWORK_ALIASES = {
    "TRC20": "TRC-20",
    "TRC-20": "TRC-20",
    "ERC20": "ERC-20",
    "ERC-20": "ERC-20",
    "BEP20": "BEP-20",
    "BEP-20": "BEP-20",
}
_WHITELIST_NETWORK_VARIANTS = {
    "TRC-20": ("TRC-20", "TRC20"),
    "ERC-20": ("ERC-20", "ERC20"),
    "BEP-20": ("BEP-20", "BEP20"),
}
_WHITELIST_ADDRESS_PATTERNS = {
    "TRC-20": re.compile(r"^T[A-Za-z1-9]{33}$"),
    "ERC-20": re.compile(r"^0x[A-Fa-f0-9]{40}$"),
    "BEP-20": re.compile(r"^0x[A-Fa-f0-9]{40}$"),
}
_WHITELIST_ADDRESS_ERRORS = {
    "TRC-20": "TRC-20 address must start with T and contain 34 characters.",
    "ERC-20": "ERC-20 address must start with 0x and contain 42 characters.",
    "BEP-20": "BEP-20 address must start with 0x and contain 42 characters.",
}
_EVM_WHITELIST_NETWORKS = {"ERC-20", "BEP-20"}
_PENDING_OR_ACTIVE_WHITELIST_STATUSES = {
    WhitelistAddressStatus.PENDING.value,
    WhitelistAddressStatus.ACTIVE.value,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def next_daily_reset_at(reference: datetime | None = None) -> datetime:
    current = (reference or utc_now()).astimezone(timezone.utc)
    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=1)


def next_monthly_reset_at(reference: datetime | None = None) -> datetime:
    current = (reference or utc_now()).astimezone(timezone.utc)
    month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        return month_start.replace(year=month_start.year + 1, month=1)
    return month_start.replace(month=month_start.month + 1)


def calculate_remaining_quota(limit_value: Decimal, used_value: Decimal) -> Decimal:
    remaining = limit_value - used_value
    if remaining < Decimal("0"):
        return Decimal("0")
    return remaining


def normalize_whitelist_network(network: str) -> str:
    normalized = str(network).strip().upper().replace("_", "").replace(" ", "")
    canonical = _WHITELIST_NETWORK_ALIASES.get(normalized)
    if canonical is None:
        raise ValueError(
            f"Unsupported whitelist network: {network}. Supported networks: {', '.join(SUPPORTED_WHITELIST_NETWORKS)}."
        )
    return canonical


def normalize_whitelist_address(network: str, address: str) -> str:
    canonical_network = normalize_whitelist_network(network)
    candidate = str(address).strip()
    if not candidate:
        raise ValueError("Whitelist address is required.")

    pattern = _WHITELIST_ADDRESS_PATTERNS[canonical_network]
    if not pattern.fullmatch(candidate):
        raise ValueError(_WHITELIST_ADDRESS_ERRORS[canonical_network])

    if canonical_network in _EVM_WHITELIST_NETWORKS:
        return candidate.lower()
    return candidate


def validate_whitelist_address_record(
    network: str,
    address: str,
    address_normalized: str | None = None,
) -> tuple[str, str]:
    canonical_network = normalize_whitelist_network(network)
    normalized_address = normalize_whitelist_address(canonical_network, address)
    if address_normalized is not None and str(address_normalized).strip() != normalized_address:
        raise ValueError("address_normalized must match the normalized address for the selected network.")
    return canonical_network, normalized_address


def get_whitelist_network_variants(network: str) -> tuple[str, ...]:
    canonical_network = normalize_whitelist_network(network)
    return _WHITELIST_NETWORK_VARIANTS[canonical_network]


def find_matching_whitelist_entry(
    existing_entries: Sequence[Mapping[str, object]],
    *,
    network: str,
    address: str,
) -> Mapping[str, object] | None:
    canonical_network, normalized_address = validate_whitelist_address_record(network, address)

    for entry in existing_entries:
        try:
            entry_network = normalize_whitelist_network(str(entry.get("network", "")))
        except ValueError:
            continue
        if entry_network != canonical_network:
            continue

        entry_address_normalized = entry.get("address_normalized")
        if entry_address_normalized is None and entry.get("address") is not None:
            try:
                entry_address_normalized = normalize_whitelist_address(entry_network, str(entry["address"]))
            except ValueError:
                continue
        elif entry_address_normalized is not None:
            try:
                entry_address_normalized = normalize_whitelist_address(entry_network, str(entry_address_normalized))
            except ValueError:
                continue

        if str(entry_address_normalized).strip() == normalized_address:
            return entry

    return None


def ensure_whitelist_entry_can_be_created(
    existing_entries: Sequence[Mapping[str, object]],
    *,
    network: str,
    address: str,
) -> tuple[str, str]:
    canonical_network, normalized_address = validate_whitelist_address_record(network, address)

    active_or_pending_count = 0
    for entry in existing_entries:
        status = str(entry.get("status", "")).strip().lower()
        if status in _PENDING_OR_ACTIVE_WHITELIST_STATUSES:
            active_or_pending_count += 1

    if active_or_pending_count >= MAX_PENDING_OR_ACTIVE_WHITELIST_ADDRESSES:
        raise ValueError(
            f"Whitelist allows at most {MAX_PENDING_OR_ACTIVE_WHITELIST_ADDRESSES} addresses in pending and active states."
        )

    existing_entry = find_matching_whitelist_entry(
        existing_entries,
        network=canonical_network,
        address=normalized_address,
    )
    if existing_entry is not None:
        status = str(existing_entry.get("status", "")).strip().lower()
        if status == WhitelistAddressStatus.REJECTED.value:
            raise ValueError("Rejected whitelist addresses cannot be submitted again.")
        raise ValueError("Whitelist address already exists for this user and network.")

    return canonical_network, normalized_address
