from datetime import datetime, timezone
from decimal import Decimal

from bot.crypto_exchange_bot import (
    _build_profile_text,
    _build_whitelist_submission_text,
    _build_whitelist_text,
)
from shared.models import LimitQuotaDB
from shared.security_settings import next_daily_reset_at, next_monthly_reset_at
from shared.types.enums import VerificationLevel


def test_build_profile_text_includes_daily_and_monthly_limits() -> None:
    quota = LimitQuotaDB(
        user_id=321,
        verification_level=VerificationLevel.EXTENDED,
        daily_limit=Decimal("10000000"),
        daily_used=Decimal("1250000"),
        daily_reset_at=next_daily_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
        monthly_limit=Decimal("50000000"),
        monthly_used=Decimal("7500000"),
        monthly_reset_at=next_monthly_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
    )

    text = _build_profile_text(
        {
            "telegram_user_id": 321,
            "username": "alice",
            "first_name": "Alice",
            "last_name": "Doe",
            "first_seen_at": datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
            "last_activity_at": datetime(2026, 4, 3, 12, 30, tzinfo=timezone.utc),
        },
        total_orders=5,
        active_orders=2,
        materials_count=1,
        quota=quota,
    )

    assert "Лимиты профиля" in text
    assert "День:" in text
    assert "Месяц:" in text
    assert "остаток" in text


def test_build_whitelist_text_states_active_only_rule() -> None:
    text = _build_whitelist_text(
        "TRC20",
        [
            {
                "id": "wla_1",
                "label": "Main",
                "address": "TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "status": "active",
            }
        ],
    )

    assert "активные адреса из whitelist" in text
    assert "Main" in text


def test_build_whitelist_submission_text_requires_moderation_before_order() -> None:
    text = _build_whitelist_submission_text("ERC20", "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    assert "не активирован" in text
    assert "статуса active" in text
    assert "Сделки и выводы доступны только" in text
    assert "Отправить адрес на модерацию" in text
