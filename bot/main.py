import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request

from .config import settings
from .crypto_exchange_bot import router as crypto_exchange_router
from .handlers import common
from .handlers.common import set_bot_commands
from .queue_consumer import (
    listen_broadcast_messages,
    listen_manager_notifications,
    listen_order_status_messages,
)
from .redis_client import close_redis_pool, get_redis_pool
from shared import db

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
WEBHOOK_LISTEN_HOST = "0.0.0.0"
WEBHOOK_LISTEN_PORT = 8081


async def on_startup(bot: Bot) -> None:
    """Actions to perform on bot startup."""
    logger.info("Starting bot. mode=%s", settings.telegram_bot_mode)
    await db.connect_db()
    await set_bot_commands(bot)
    get_redis_pool()
    asyncio.create_task(listen_broadcast_messages(bot))
    asyncio.create_task(listen_order_status_messages(bot))
    asyncio.create_task(listen_manager_notifications(bot))
    logger.info("Redis queue listeners started.")


async def on_shutdown(bot: Bot) -> None:
    """Actions to perform on bot shutdown."""
    logger.info("Stopping bot. mode=%s", settings.telegram_bot_mode)
    await db.disconnect_db()
    await close_redis_pool()
    await bot.session.close()
    logger.info("Bot stopped.")


def validate_runtime_settings() -> None:
    if not settings.telegram_bot_token or settings.telegram_bot_token == "DEFINE_ME":
        raise SystemExit("TELEGRAM_BOT_TOKEN is not defined in settings.")
    if not settings.mongo_uri:
        raise SystemExit("MONGO_URI is not defined in settings.")
    settings.validate_telegram_webhook_settings()


def create_bot() -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(
        settings.redis_url,
        state_ttl=timedelta(minutes=settings.fsm_timeout_minutes),
        data_ttl=timedelta(minutes=settings.fsm_timeout_minutes),
    )
    dispatcher = Dispatcher(storage=storage)
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)
    dispatcher.include_router(common.router)
    dispatcher.include_router(crypto_exchange_router)
    return dispatcher


async def configure_webhook(bot: Bot, dispatcher: Dispatcher) -> None:
    webhook_secret = settings.telegram_webhook_secret
    if webhook_secret is None:
        raise ValueError("TELEGRAM_WEBHOOK_SECRET is required in webhook mode.")
    await bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=webhook_secret,
        allowed_updates=dispatcher.resolve_used_update_types(),
        drop_pending_updates=False,
    )
    logger.info("Telegram webhook configured. url=%s", settings.telegram_webhook_url)


async def remove_webhook(bot: Bot) -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    logger.info("Telegram webhook removed.")


def create_webhook_app(bot: Bot, dispatcher: Dispatcher) -> FastAPI:
    settings.validate_telegram_webhook_settings()
    webhook_secret = settings.telegram_webhook_secret
    if webhook_secret is None:
        raise ValueError("TELEGRAM_WEBHOOK_SECRET is required in webhook mode.")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await dispatcher.emit_startup(bot=bot)
        await configure_webhook(bot, dispatcher)
        try:
            yield
        finally:
            await remove_webhook(bot)
            await dispatcher.emit_shutdown(bot=bot)

    app = FastAPI(title="Telegram Bot Webhook", lifespan=lifespan)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "mode": settings.telegram_bot_mode}

    @app.post(settings.telegram_webhook_path)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if x_telegram_bot_api_secret_token != webhook_secret:
            logger.error("Rejected Telegram webhook request due to invalid secret header.")
            raise HTTPException(status_code=403, detail="Invalid webhook secret.")
        update_payload = await request.json()
        update = Update.model_validate(update_payload, context={"bot": bot})
        await dispatcher.feed_update(bot, update)
        return {"ok": True}

    return app


async def run_polling() -> None:
    bot = create_bot()
    dispatcher = create_dispatcher()
    await remove_webhook(bot)
    await dispatcher.start_polling(bot)


def run_webhook() -> None:
    bot = create_bot()
    dispatcher = create_dispatcher()
    webhook_app = create_webhook_app(bot, dispatcher)
    uvicorn.run(
        webhook_app,
        host=WEBHOOK_LISTEN_HOST,
        port=WEBHOOK_LISTEN_PORT,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    validate_runtime_settings()
    if settings.telegram_bot_mode == "webhook":
        run_webhook()
        return
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
