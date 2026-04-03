from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from shared.config import settings
from shared.types.enums import ExchangeType, OrderStatus

CRYPTO_CURRENCIES = ("USDT", "BTC", "ETH")
FIAT_CURRENCIES = ("RUB",)

EXCHANGE_TYPE_META = {
    ExchangeType.CRYPTO_TO_FIAT.value: {"label": "Crypto -> Fiat", "emoji": "💰"},
    ExchangeType.FIAT_TO_CRYPTO.value: {"label": "Fiat -> Crypto", "emoji": "💵"},
    ExchangeType.CRYPTO_TO_CRYPTO.value: {"label": "Crypto -> Crypto", "emoji": "🔄"},
}

ORDER_STATUS_META = {
    OrderStatus.NEW.value: {"label": "New", "emoji": "⚪"},
    OrderStatus.PROCESSING.value: {"label": "In progress", "emoji": "🟡"},
    OrderStatus.WAITING_PAYMENT.value: {"label": "Waiting for payment", "emoji": "🟠"},
    OrderStatus.COMPLETED.value: {"label": "Completed", "emoji": "🟢"},
    OrderStatus.CANCELLED.value: {"label": "Cancelled", "emoji": "🔴"},
}

NETWORK_OPTIONS = {
    "USDT": (
        {"code": "TRC20", "label": "TRC-20 (fee 1 USDT)"},
        {"code": "ERC20", "label": "ERC-20 (fee 5 USDT)"},
        {"code": "BEP20", "label": "BEP-20 (fee 0.5 USDT)"},
    ),
    "BTC": (
        {"code": "BTC", "label": "Bitcoin Network"},
    ),
    "ETH": (
        {"code": "ETH", "label": "Ethereum Network"},
        {"code": "POLYGON", "label": "Polygon"},
    ),
    "RUB": (
        {"code": "BANK", "label": "Bank transfer"},
    ),
}

_AMOUNT_RE = re.compile(r"^\d+(?:[.,]\d+)?$")
_ADDRESS_PATTERNS = {
    ("USDT", "TRC20"): (re.compile(r"^T[A-Za-z1-9]{33}$"), "USDT TRC-20 address must start with T and contain 34 characters."),
    ("USDT", "ERC20"): (re.compile(r"^0x[A-Fa-f0-9]{40}$"), "USDT ERC-20 address must start with 0x and contain 42 characters."),
    ("USDT", "BEP20"): (re.compile(r"^0x[A-Fa-f0-9]{40}$"), "USDT BEP-20 address must start with 0x and contain 42 characters."),
    ("BTC", "BTC"): (re.compile(r"^(1|3|bc1)[A-Za-z0-9]{25,61}$"), "Bitcoin address format is invalid."),
    ("ETH", "ETH"): (re.compile(r"^0x[A-Fa-f0-9]{40}$"), "Ethereum address must start with 0x and contain 42 characters."),
    ("ETH", "POLYGON"): (re.compile(r"^0x[A-Fa-f0-9]{40}$"), "Polygon address must start with 0x and contain 42 characters."),
}


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _normalize_decimal(value: str) -> Optional[Decimal]:
    cleaned = value.replace(" ", "").strip()
    if not cleaned or not _AMOUNT_RE.fullmatch(cleaned):
        return None
    return Decimal(cleaned.replace(",", "."))


def get_exchange_type_label(exchange_type: str) -> str:
    return EXCHANGE_TYPE_META[exchange_type]["label"]


def get_exchange_type_emoji(exchange_type: str) -> str:
    return EXCHANGE_TYPE_META[exchange_type]["emoji"]


def get_order_status_label(status: str) -> str:
    return ORDER_STATUS_META[status]["label"]


def get_order_status_emoji(status: str) -> str:
    return ORDER_STATUS_META[status]["emoji"]


def get_available_from_currencies(exchange_type: str) -> tuple[str, ...]:
    if exchange_type == ExchangeType.CRYPTO_TO_FIAT.value:
        return CRYPTO_CURRENCIES
    if exchange_type == ExchangeType.FIAT_TO_CRYPTO.value:
        return FIAT_CURRENCIES
    return CRYPTO_CURRENCIES


def get_available_to_currencies(exchange_type: str, from_currency: str) -> tuple[str, ...]:
    if exchange_type == ExchangeType.CRYPTO_TO_FIAT.value:
        return FIAT_CURRENCIES
    if exchange_type == ExchangeType.FIAT_TO_CRYPTO.value:
        return CRYPTO_CURRENCIES
    return tuple(currency for currency in CRYPTO_CURRENCIES if currency != from_currency)


def get_network_currency(exchange_type: str, from_currency: str, to_currency: str) -> str:
    if to_currency in CRYPTO_CURRENCIES:
        return to_currency
    if exchange_type == ExchangeType.CRYPTO_TO_FIAT.value:
        return from_currency
    return "RUB"


def get_network_options(exchange_type: str, from_currency: str, to_currency: str) -> tuple[dict, ...]:
    network_currency = get_network_currency(exchange_type, from_currency, to_currency)
    return NETWORK_OPTIONS[network_currency]


def get_network_label(currency: str, network_code: str) -> str:
    for option in NETWORK_OPTIONS[currency]:
        if option["code"] == network_code:
            return option["label"]
    return network_code


def get_exchange_rate(from_currency: str, to_currency: str) -> Decimal:
    if from_currency == to_currency:
        raise ValueError("Source and destination currencies must differ.")

    rub_rates = {
        "RUB": Decimal("1"),
        "USDT": settings.rates_usdt_rub,
        "BTC": settings.rates_btc_rub,
        "ETH": settings.rates_eth_rub,
    }
    if from_currency not in rub_rates or to_currency not in rub_rates:
        raise ValueError(f"Unsupported rate pair: {from_currency} -> {to_currency}")
    return _quantize(rub_rates[from_currency] / rub_rates[to_currency], "0.00000001")


def validate_amount(amount_text: str, from_currency: str) -> tuple[bool, str, Optional[Decimal]]:
    amount = _normalize_decimal(amount_text)
    if amount is None or amount <= 0:
        return False, "Enter a valid numeric amount.", None

    amount_in_rub = amount
    if from_currency != "RUB":
        amount_in_rub = _quantize(amount * get_exchange_rate(from_currency, "RUB"), "0.01")

    if amount_in_rub < settings.min_exchange_amount_rub or amount_in_rub > settings.max_exchange_amount_rub:
        return (
            False,
            f"Incorrect amount. Enter a value equivalent to {format_money(settings.min_exchange_amount_rub, 'RUB')} - {format_money(settings.max_exchange_amount_rub, 'RUB')}.",
            None,
        )

    return True, "", amount


def validate_address(exchange_type: str, from_currency: str, to_currency: str, network: str, address: str) -> tuple[bool, str]:
    normalized = address.strip()
    if not normalized:
        return False, "Address or payment details are required."

    validation_currency = to_currency if to_currency in CRYPTO_CURRENCIES else "RUB"
    if validation_currency == "RUB":
        if len(normalized) < 10:
            return False, "Bank details are too short."
        return True, ""

    pattern_key = (validation_currency, network)
    if pattern_key not in _ADDRESS_PATTERNS:
        return False, "Unsupported currency or network."

    pattern, error_message = _ADDRESS_PATTERNS[pattern_key]
    if not pattern.fullmatch(normalized):
        return False, error_message
    return True, ""


def calculate_order_preview(
    from_currency: str,
    to_currency: str,
    amount: Decimal,
) -> dict:
    rate = get_exchange_rate(from_currency, to_currency)
    gross_receive_amount = amount * rate
    fee_amount = _quantize(gross_receive_amount * settings.default_fee_percent / Decimal("100"), "0.01")
    receive_amount = _quantize(gross_receive_amount - fee_amount, "0.01")
    return {
        "rate": _quantize(rate, "0.00000001"),
        "gross_receive_amount": _quantize(gross_receive_amount, "0.01"),
        "fee_amount": fee_amount,
        "receive_amount": receive_amount,
    }


def format_money(amount: Decimal, currency: str) -> str:
    if currency == "RUB":
        normalized = _quantize(amount, "0.01")
        return f"{normalized:,.2f} {currency}".replace(",", " ")
    if currency in {"BTC", "ETH"}:
        normalized = _quantize(amount, "0.00000001")
        return f"{normalized:.8f} {currency}"
    normalized = _quantize(amount, "0.01")
    return f"{normalized:,.2f} {currency}".replace(",", " ")


def format_rate(rate: Decimal, from_currency: str, to_currency: str) -> str:
    if from_currency in {"BTC", "ETH"} or to_currency in {"BTC", "ETH"}:
        return f"{_quantize(rate, '0.00000001')}"
    return f"{_quantize(rate, '0.0000')}"


def format_datetime_for_user(value: datetime) -> str:
    local_value = value.astimezone()
    return local_value.strftime("%d.%m.%Y %H:%M")


def get_rates_snapshot() -> list[tuple[str, str, Decimal]]:
    pairs = [
        ("USDT", "RUB"),
        ("BTC", "RUB"),
        ("ETH", "RUB"),
        ("USDT", "BTC"),
        ("BTC", "USDT"),
        ("ETH", "USDT"),
    ]
    return [(base, quote, get_exchange_rate(base, quote)) for base, quote in pairs]
