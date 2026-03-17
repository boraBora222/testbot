import asyncio
import json
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# Import local modules
from .redis_client import get_redis_client
from .config import settings
from shared import db
from shared.types.enums import ApplicationStatus
from shared.db import is_user_banned

logger = logging.getLogger(__name__)

async def process_notification_message(message_data: dict, bot: Bot):
    """Processes a single notification message received from Redis."""
    try:
        app_id = message_data['application_id']
        user_id = message_data['user_id']
        status = ApplicationStatus(message_data['status']) # Convert back to enum
        comment = message_data.get('moderation_comment')
        
        logger.info(f"Processing notification for app {app_id}, user {user_id}, status {status}")

        notification_text = ""
        invite_link = None
        error_message = None

        if status == ApplicationStatus.APPROVED:
            notification_text = "🎉 Поздравляем! Ваша заявка одобрена."
            if settings.target_chat_id:
                try:
                    # Generate invite link (expires after 1 hour, 1 use)
                    link = await bot.create_chat_invite_link(
                        chat_id=settings.target_chat_id,
                        member_limit=1,
                        # expire_date=datetime.now() + timedelta(hours=1) # Optional expiry
                    )
                    invite_link = link.invite_link
                    notification_text += f"\n\n🔗 Ссылка-приглашение (действует 1 раз): {invite_link}"
                    logger.info(f"Generated invite link for app {app_id}")
                except Exception as e:
                    logger.exception(f"Failed to create invite link for app {app_id}, chat {settings.target_chat_id}: {e}")
                    error_message = f"Failed to create invite link: {e}"
                    # Send notification without link in this case
                    notification_text += "\n\n(Не удалось создать ссылку-приглашение. Обратитесь к администратору.)"
            else:
                logger.warning(f"TARGET_CHAT_ID not set. Cannot generate invite link for approved app {app_id}.")
                notification_text += "\n\n(Ссылка-приглашение не может быть создана, обратитесь к администратору.)"

        elif status == ApplicationStatus.REJECTED:
            notification_text = "❌ К сожалению, ваша заявка отклонена."
            if comment:
                notification_text += f"\n\nПричина: {comment}"
        else:
            logger.warning(f"Received unexpected status '{status}' for app {app_id}. Skipping.")
            # Mark as notified even if skipped to avoid reprocessing
            await db.set_application_notified(app_id, error=f"Unexpected status: {status}")
            return

        # Try sending the notification to the user
        try:
            await bot.send_message(chat_id=user_id, text=notification_text, disable_web_page_preview=True)
            logger.info(f"Sent {status.value} notification to user {user_id} for app {app_id}")
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            # User blocked the bot, chat not found, etc.
            logger.error(f"Failed to send notification to user {user_id} for app {app_id}: {e}")
            error_message = f"Telegram API Error: {e.__class__.__name__} - {e}"
        except Exception as e:
            # Other unexpected errors
            logger.exception(f"Unexpected error sending notification to user {user_id} for app {app_id}: {e}")
            error_message = f"Unexpected Error: {e.__class__.__name__} - {e}"

        # Mark as notified in DB, recording any error
        await db.set_application_notified(app_id, error=error_message)

    except Exception as e:
        logger.exception(f"Critical error processing notification message: {message_data}. Error: {e}")
        # Optionally: Move message to a dead-letter queue or log extensively
        # Avoid marking as notified if basic parsing failed

async def listen_application_updates(bot: Bot):
    """Listens to the Redis list queue for application updates and processes them."""
    redis_client = get_redis_client()
    queue_name = settings.redis_queue_name
    
    logger.info(f"Starting notification consumer on queue '{queue_name}'...")

    while True:
        try:
            # Use blocking list pop (BLPOP) to wait for messages indefinitely
            # BLPOP returns a tuple (queue_name, message) or None on timeout (not used here)
            message = await redis_client.blpop(queue_name) 
            if not message:
                continue # Should not happen with timeout=0

            _queue, msg_data = message # Unpack the tuple
            logger.debug(f"Received message from {queue_name}: {msg_data}")
            
            message_data = json.loads(msg_data)
            
            # Process the message
            await process_notification_message(message_data, bot)

            # Simple rate limiting
            # TODO: Implement more robust rate limiting if needed
            await asyncio.sleep(1.0) # Sleep for 1 second between processing messages

        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}. Reconnecting...")
            # Implement reconnection logic if needed, or rely on Redis client library
            await asyncio.sleep(5) # Wait before retrying
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message from Redis: {message}. Error: {e}")
            # Decide how to handle malformed messages (e.g., log and skip)
        except Exception as e:
            logger.exception(f"Unexpected error in Redis listener loop: {e}")
            await asyncio.sleep(5) # Wait before continuing loop on general errors


# --- Broadcast Message Consumer ---

async def process_broadcast_message(message_data: dict, bot: Bot):
    """Processes a single broadcast message received from Redis."""
    try:
        if message_data.get("type") != "broadcast":
            logger.warning(f"Received non-broadcast message in broadcast queue: {message_data}")
            return

        user_id = message_data['user_id']
        text = message_data['text']

        logger.info(f"Processing broadcast message for user {user_id}")

        # Skip if user is banned
        try:
            if await is_user_banned(int(user_id)):
                logger.info(f"Skipping broadcast for banned user {user_id}")
                return
        except Exception:
            # If check fails, proceed to send to avoid silent drops due to infra error
            pass

        # Try sending the message to the user
        try:
            await bot.send_message(chat_id=user_id, text=text)
            logger.info(f"Sent broadcast message to user {user_id}")
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            # User blocked the bot, chat not found, etc.
            logger.error(f"Failed to send broadcast message to user {user_id}: {e}")
            # No need to update DB status here, just log
        except Exception as e:
            # Other unexpected errors
            logger.exception(f"Unexpected error sending broadcast message to user {user_id}: {e}")

    except KeyError as e:
        logger.error(f"Missing key {e} in broadcast message data: {message_data}")
    except Exception as e:
        logger.exception(f"Critical error processing broadcast message: {message_data}. Error: {e}")


async def listen_broadcast_messages(bot: Bot):
    """Listens to the Redis list queue for broadcast messages and processes them."""
    redis_client = get_redis_client()
    # Use the specific queue name from settings
    queue_name = settings.broadcast_queue_name
    if not queue_name:
        logger.error("BROADCAST_QUEUE_NAME is not set in settings. Broadcast listener cannot start.")
        return

    logger.info(f"Starting broadcast message consumer on queue '{queue_name}'...")

    while True:
        try:
            # Use blocking list pop (BLPOP) to wait for messages indefinitely
            message = await redis_client.blpop(queue_name)
            if not message:
                continue

            _queue, msg_data = message
            logger.debug(f"Received message from {queue_name}: {msg_data}")

            try:
                message_data = json.loads(msg_data)
                # Process the message
                await process_broadcast_message(message_data, bot)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON message from broadcast queue: {msg_data}. Error: {e}")

            # Simple rate limiting to avoid hitting Telegram limits too quickly
            await asyncio.sleep(0.1) # Sleep for 100ms between messages

        except redis.ConnectionError as e:
            logger.error(f"Redis connection error in broadcast listener: {e}. Reconnecting...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error in broadcast listener loop: {e}")
            await asyncio.sleep(5)
