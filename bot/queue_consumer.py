import asyncio
import json
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from redis.exceptions import ConnectionError as RedisConnectionError
from shared import db
from shared.types.enums import OrderStatus

from .config import settings
from .exchange_logic import (
    get_order_status_emoji,
    get_order_status_label,
)
from .redis_client import get_redis_client

logger = logging.getLogger(__name__)


async def _send_manager_notification(bot: Bot, payload: dict) -> None:
    text = ""
    attachment = None
    send_photo = False
    send_document = False

    if payload["event"] == "new_order":
        username = f"@{payload['username']}" if payload.get("username") else f"ID: {payload['user_id']}"
        text = (
            "🔔 Новая заявка\n\n"
            f"Клиент: {username}\n"
            f"Order: {payload['order_id']}\n"
            f"Summary: {payload['summary']}"
        )
    elif payload["event"] == "support_message":
        username = f"@{payload['username']}" if payload.get("username") else f"ID: {payload['user_id']}"
        text = (
            "🔔 Новое обращение в поддержку\n\n"
            f"Клиент: {username}\n\n"
            f"Сообщение:\n{payload.get('text') or '(без текста)'}"
        )
        attachment = payload.get("file_id")
        send_photo = payload.get("content_type") == "photo"
        send_document = payload.get("content_type") == "document"
    elif payload["event"] == "material_received":
        username = f"@{payload['username']}" if payload.get("username") else f"ID: {payload['user_id']}"
        text = (
            "📎 Получен материал от пользователя\n\n"
            f"Клиент: {username}\n"
            f"Тип: {payload['content_type']}\n"
            f"Описание: {payload.get('text') or '-'}"
        )
        attachment = payload.get("file_id")
        send_photo = payload.get("content_type") == "photo"
        send_document = payload.get("content_type") == "document"
    else:
        logger.warning("Unknown manager notification event: %s", payload.get("event"))
        return

    for master_user_id in settings.master_user_ids_list:
        try:
            if attachment and send_photo:
                await bot.send_photo(chat_id=master_user_id, photo=attachment, caption=text)
            elif attachment and send_document:
                await bot.send_document(chat_id=master_user_id, document=attachment, caption=text)
            else:
                await bot.send_message(chat_id=master_user_id, text=text)
        except (TelegramForbiddenError, TelegramBadRequest):
            logger.exception("Failed to notify manager %s", master_user_id)


async def process_order_status_message(message_data: dict, bot: Bot) -> None:
    """Processes a single order status change message received from Redis."""
    try:
        order_id = message_data["order_id"]
        new_status = OrderStatus(message_data["new_status"])
        reason = message_data.get("reason")
    except (KeyError, ValueError):
        logger.exception("Invalid order status payload: %s", message_data)
        return

    updated_order = await db.update_order_status_by_order_id(order_id, new_status)
    if not updated_order:
        logger.warning("Order not found for status update: %s", order_id)
        return

    text = (
        f"📦 Статус заявки #{order_id} изменён\n\n"
        f"Новый статус: {get_order_status_emoji(new_status.value)} {get_order_status_label(new_status.value)}"
    )
    if reason:
        text += f"\nПричина: {reason}"

    try:
        await bot.send_message(chat_id=updated_order["user_id"], text=text)
    except (TelegramForbiddenError, TelegramBadRequest):
        logger.exception("Failed to send order status update for %s", order_id)


async def process_broadcast_message(message_data: dict, bot: Bot) -> None:
    """Processes a single broadcast message received from Redis."""
    try:
        if message_data.get("type") != "broadcast":
            logger.warning("Received non-broadcast message in broadcast queue: %s", message_data)
            return
        await bot.send_message(chat_id=message_data["user_id"], text=message_data["text"])
    except (KeyError, TelegramForbiddenError, TelegramBadRequest):
        logger.exception("Failed to process broadcast message: %s", message_data)


async def process_manager_notification(message_data: dict, bot: Bot) -> None:
    """Processes manager notification events received from Redis."""
    if message_data.get("type") != "notify_managers":
        logger.warning("Received non-manager payload in manager queue: %s", message_data)
        return
    await _send_manager_notification(bot, message_data)


async def _listen_queue(queue_name: str, processor, bot: Bot, queue_label: str) -> None:
    redis_client = get_redis_client()
    logger.info("Starting %s consumer on queue '%s'.", queue_label, queue_name)
    while True:
        try:
            message = await redis_client.blpop(queue_name)
            if not message:
                continue
            _queue, raw_payload = message
            payload = json.loads(raw_payload)
            await processor(payload, bot)
            await asyncio.sleep(0.1)
        except RedisConnectionError:
            logger.exception("Redis connection error in %s consumer.", queue_label)
            await asyncio.sleep(5)
        except json.JSONDecodeError:
            logger.exception("Failed to decode JSON in %s consumer.", queue_label)
        except Exception:
            logger.exception("Unexpected error in %s consumer.", queue_label)
            await asyncio.sleep(1)


async def listen_broadcast_messages(bot: Bot) -> None:
    await _listen_queue(settings.broadcast_queue_name, process_broadcast_message, bot, "broadcast")


async def listen_order_status_messages(bot: Bot) -> None:
    await _listen_queue(settings.order_status_queue_name, process_order_status_message, bot, "order-status")


async def listen_manager_notifications(bot: Bot) -> None:
    await _listen_queue(settings.notify_managers_queue_name, process_manager_notification, bot, "manager")
