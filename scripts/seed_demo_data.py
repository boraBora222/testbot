import asyncio
from decimal import Decimal

from shared import db
from shared.models import OrderDB
from shared.types.enums import ExchangeType


async def seed() -> None:
    await db.connect_db()
    try:
        await db.ensure_exchange_user(
            telegram_user_id=123456789,
            username="demo_user",
            first_name="Demo",
            last_name="User",
        )
        existing_order = await db.get_order_by_order_id("ORD-00001")
        if existing_order is None:
            order = OrderDB(
                order_id="ORD-00001",
                user_id=123456789,
                username="demo_user",
                exchange_type=ExchangeType.CRYPTO_TO_FIAT,
                from_currency="USDT",
                to_currency="RUB",
                amount=Decimal("1000"),
                network="TRC20",
                address="Demo bank details",
                rate=Decimal("92.5000"),
                fee_percent=Decimal("0.5"),
                fee_amount=Decimal("46.25"),
                receive_amount=Decimal("92453.75"),
                is_demo=True,
            )
            await db.create_order(order)
            print("Seeded demo order ORD-00001")
        else:
            print("Demo order ORD-00001 already exists")
    finally:
        await db.disconnect_db()


if __name__ == "__main__":
    asyncio.run(seed())
