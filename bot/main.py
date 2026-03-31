import asyncio
import logging
import sys
from datetime import timedelta

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage

from .config import settings
from .handlers import common
from .handlers.common import set_bot_commands
from .crypto_exchange_bot import router as crypto_exchange_router
from .redis_client import get_redis_pool, close_redis_pool
from .queue_consumer import (
    listen_broadcast_messages,
    listen_manager_notifications,
    listen_order_status_messages,
)
from shared import db

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Actions to perform on bot startup."""
    logger.info("Starting bot...")
    await db.connect_db()
    await set_bot_commands(bot)
    get_redis_pool()
    asyncio.create_task(listen_broadcast_messages(bot))
    asyncio.create_task(listen_order_status_messages(bot))
    asyncio.create_task(listen_manager_notifications(bot))
    logger.info("Redis queue listeners started.")


async def on_shutdown(bot: Bot):
    """Actions to perform on bot shutdown."""
    logger.info("Stopping bot...")
    await db.disconnect_db()
    await close_redis_pool()
    await bot.session.close()
    logger.info("Bot stopped.")


async def main() -> None:
    """Main function to initialize and run the bot."""
    if not settings.telegram_bot_token or settings.telegram_bot_token == "DEFINE_ME":
        logger.critical("TELEGRAM_BOT_TOKEN is not defined in settings. Exiting.")
        sys.exit(1)
    if not settings.mongo_uri:
        logger.critical("MONGO_URI is not defined in settings. Exiting.")
        sys.exit(1)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage.from_url(
        settings.redis_url,
        state_ttl=timedelta(minutes=settings.fsm_timeout_minutes),
        data_ttl=timedelta(minutes=settings.fsm_timeout_minutes),
    )
    dp = Dispatcher(storage=storage)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.include_router(common.router)
    dp.include_router(crypto_exchange_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot polling interrupted.")
