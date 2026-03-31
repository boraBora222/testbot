from decimal import Decimal

from bot.exchange_logic import calculate_order_preview, get_exchange_rate, validate_amount
from shared.config import settings


def test_get_exchange_rate_uses_demo_rub_anchor() -> None:
    assert get_exchange_rate("USDT", "RUB") == settings.rates_usdt_rub


def test_validate_amount_rejects_values_below_minimum() -> None:
    is_valid, error_message, amount = validate_amount("9999", "RUB")

    assert is_valid is False
    assert amount is None
    assert "Incorrect amount" in error_message


def test_calculate_order_preview_applies_fee_to_receive_amount() -> None:
    preview = calculate_order_preview("RUB", "USDT", Decimal("100000"))

    expected_rate = get_exchange_rate("RUB", "USDT")
    expected_gross = Decimal("100000") * expected_rate
    expected_fee = (expected_gross * settings.default_fee_percent / Decimal("100")).quantize(Decimal("0.01"))
    expected_receive = (expected_gross - expected_fee).quantize(Decimal("0.01"))

    assert preview["gross_receive_amount"] == expected_gross.quantize(Decimal("0.01"))
    assert preview["fee_amount"] == expected_fee
    assert preview["receive_amount"] == expected_receive
