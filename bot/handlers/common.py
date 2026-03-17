import logging
from typing import List
import html # Added import

from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command
from datetime import datetime, timezone # Added timezone
# Removed FSMContext import as it's no longer needed for submission
from aiogram.types import BotCommand # Removed InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

# Removed FSM state import
# from bot.states import LinkSubmissionFSM
# Import DB access and models
from shared.db import get_db, is_user_banned
from shared.models import LinkDB, BotUser # Added BotUser
# Import settings
from shared.config import settings

logger = logging.getLogger(__name__)

# Create a router instance for common handlers
router = Router(name="common_handlers")


# --- Helper Function to Update User Activity ---

async def update_user_activity(user: types.User):
    """
    Creates or updates the user's record in the bot_users collection.
    Called on user interaction like /start.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    try:
        await db.bot_users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "last_seen_at": now,
                },
                "$setOnInsert": {
                    "first_seen_at": now,
                }
            },
            upsert=True
        )
        logger.debug(f"Updated activity for user {user.id}")
    except Exception as e:
        logger.exception(f"Failed to update activity for user {user.id}: {e}")


# --- Bot Commands Setup ---

async def set_bot_commands(bot: Bot):
    """Sets the bot commands in the Telegram menu."""
    commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        # Removed submit_link command
        BotCommand(command="stop", description="Прекратить работу и удалить данные"),
        # Add other commands if needed
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("Bot commands updated successfully.")
    except TelegramAPIError as e:
        logger.error(f"Failed to set bot commands: {e}")

# --- Helper Function to Notify Masters ---

async def notify_master_users(bot: Bot, link_data: LinkDB, link_id: str):
    """Sends a notification about a new link to master users."""
    try:
        master_ids_str = settings.master_user_ids
        master_ids = [int(uid.strip()) for uid in master_ids_str.split(',') if uid.strip().isdigit()]
    except Exception as e:
        logger.error(f"Could not parse MASTER_USER_IDS: {e}. Value: '{settings.master_user_ids}'")
        return

    if not master_ids:
        logger.warning("MASTER_USER_IDS is not set or empty. No notifications will be sent.")
        return

    web_base_url = settings.web_base_url.rstrip('/')
    admin_link = f"{web_base_url}" # Link to the list page for now
    # If you implement individual link pages later:
    # admin_link = f"{web_base_url}/links/{link_id}"

    # Escape user data for HTML safety
    # Escape user data for HTML safety
    safe_username = html.escape(f"@{link_data.username}" if link_data.username else f"ID: {link_data.user_id}")
    safe_first_name = html.escape(link_data.first_name or "")
    safe_admin_link = html.escape(admin_link) # Escape the link itself just in case

    message_text = ""
    send_method = bot.send_message # Default to sending text message

    if link_data.content_type == 'text':
        safe_content = html.escape(link_data.text or "")
        message_text = (
            f"Поступил новый материал (текст) от {safe_username} ({safe_first_name}).\n\n"
            f"<b>Текст:</b>\n<pre>{safe_content}</pre>\n\n"
            f'<a href="{safe_admin_link}">Посмотреть в админке</a>'
        )
        send_args = {"text": message_text, "parse_mode": 'HTML'}
    elif link_data.content_type == 'photo':
        safe_caption = html.escape(link_data.caption or "Без подписи")
        message_text = (
            f"Поступил новый материал (фото) от {safe_username} ({safe_first_name}).\n\n"
            f"<b>Подпись:</b>\n<pre>{safe_caption}</pre>\n\n"
            f'<a href="{safe_admin_link}">Посмотреть в админке</a>'
        )
        # Check if it was originally a document (image sent as file)
        if link_data.mime_type and link_data.mime_type.startswith('image/'):
            send_method = bot.send_document
            send_args = {"document": link_data.telegram_file_id, "caption": message_text, "parse_mode": 'HTML'}
            logger.debug(f"Notification for link {link_id} will be sent as document.")
        else: # It was sent as a photo originally
            send_method = bot.send_photo
            send_args = {"photo": link_data.telegram_file_id, "caption": message_text, "parse_mode": 'HTML'}
            logger.debug(f"Notification for link {link_id} will be sent as photo.")
    else:
        logger.warning(f"Unknown content type '{link_data.content_type}' for link {link_id}. Cannot notify masters.")
        return

    for user_id in master_ids:
        try:
            await send_method(chat_id=user_id, **send_args)
            logger.info(f"Sent notification for link {link_id} (type: {link_data.content_type}) to master user {user_id}")
        except TelegramAPIError as e:
            # Handle specific errors like chat not found, bot blocked, etc.
            logger.error(f"Failed to send notification to master user {user_id} via {send_method.__name__}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred sending notification to {user_id} via {send_method.__name__}: {e}")


# --- Start Command Handler ---

@router.message(CommandStart())
async def handle_start(message: types.Message): # Removed state: FSMContext
    """Handles the /start command and updates user activity."""
    user = message.from_user
    user_name = user.full_name or f"User {user.id}"
    logger.info(f"User {user_name} (ID: {user.id}) started the bot.")

    # Update user activity in DB
    await update_user_activity(user)

    # Removed state clearing as FSM is not used for submission
    # await state.clear()

    # Removed inline keyboard

    welcome_text = (
        f"Привет, {user_name}!\n\n"
        "Я помогу передать мистеру X ссылки, истории, текст или фото.\n"
        "Просто отправьте их мне в любое время."
    )
    # Removed reply_markup=keyboard
    await message.answer(text=welcome_text)


# --- Stop Command Handler ---

@router.message(Command("stop"))
async def handle_stop(message: types.Message): # Removed state: FSMContext
    """Handles the /stop command, removing user data."""
    user_id = message.from_user.id
    logger.info(f"User {user_id} requested /stop.")

    # Removed state clearing
    # await state.clear()

    # Attempt to delete user data from the database
    try:
        db = get_db()
        result = await db.bot_users.delete_one({"user_id": user_id})
        if result.deleted_count > 0:
            logger.info(f"Successfully deleted data for user {user_id}.")
            await message.answer("Ваши данные были удалены из системы. Чтобы начать заново, используйте /start.")
        else:
            logger.warning(f"No data found to delete for user {user_id} upon /stop command.")
            await message.answer("Ваши данные не найдены в системе. Чтобы начать, используйте /start.")
    except Exception as e:
        logger.exception(f"Failed to delete data for user {user_id} on /stop: {e}")
        await message.answer("Произошла ошибка при удалении ваших данных. Пожалуйста, попробуйте позже.")


# --- Removed Submit Link Command Handler ---


# --- Removed Submit Link Callback Handler ---


# --- Text Message Handler (always active) ---

# Removed state filter LinkSubmissionFSM.waiting_for_link
@router.message(F.text) # Filter for text messages only
async def handle_link_message(message: types.Message, bot: Bot): # Removed state: FSMContext
    """Handles any text message containing the link/text."""
    user = message.from_user
    link_text = message.text

    if not link_text: # Should not happen with F.text, but good practice
        await message.answer("Пожалуйста, пришлите текст или ссылку.")
        return

    logger.info(f"Received text from user {user.id}: '{link_text[:50]}...'")

    # Silent ban check
    try:
        if await is_user_banned(user.id):
            await message.answer("✅ Материал получен и передан.")
            # Do not save or notify for banned users
            return
    except Exception:
        # On failure to check ban, proceed normally but log inside is_user_banned
        pass

    # Prepare data for DB
    link_data = LinkDB(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        text=link_text,
        content_type='text' # Explicitly set content type
    )

    # Save to MongoDB
    try:
        db = get_db() # Remove await here, get_db likely returns the object directly
        result = await db.links.insert_one(link_data.model_dump(by_alias=True)) # Keep await for the async DB operation
        link_id = str(result.inserted_id)
        logger.info(f"Link from user {user.id} saved to DB with ID: {link_id}")

        # Send simple confirmation FIRST
        await message.answer("✅ Материал получен и передан.")

        # Removed state clearing

        # Update user activity after successful link submission
        await update_user_activity(user)
        logger.info(f"Updated activity for user {user.id} after link submission.")

        # Notify master users (run asynchronously)
        await notify_master_users(bot=bot, link_data=link_data, link_id=link_id)

    except Exception as e:
        # Log the specific error after DB save
        logger.exception(f"Error processing text link for user {user.id} after DB save (link_id: {link_id}): {e}")
        # Attempt to notify user about the error, but confirmation was already sent
        try:
            await message.answer("Произошла ошибка при обработке вашего материала после сохранения. Администраторы уведомлены.")
        except Exception as notify_err:
            logger.error(f"Failed to notify user {user.id} about post-save error: {notify_err}")
        # Removed state clearing
        # Removed state clearing


# --- Photo Message Handler (always active) ---

# Removed state filter LinkSubmissionFSM.waiting_for_link
@router.message(F.photo) # Filter for photo messages only
async def handle_link_photo(message: types.Message, bot: Bot): # Removed state: FSMContext
    """Handles any photo message."""
    user = message.from_user
    photo_file_id = message.photo[-1].file_id # Get file_id of the largest photo
    caption = message.caption

    logger.info(f"Received photo from user {user.id}. File ID: {photo_file_id}, Caption: '{caption[:50] if caption else ''}...'")

    # Silent ban check
    try:
        if await is_user_banned(user.id):
            await message.answer("✅ Материал получен и передан.")
            return
    except Exception:
        pass

    # Prepare data for DB
    link_data = LinkDB(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        telegram_file_id=photo_file_id,
        caption=caption,
        content_type='photo' # Explicitly set content type
    )

    # Save to MongoDB
    try:
        db = get_db()
        result = await db.links.insert_one(link_data.model_dump(by_alias=True))
        link_id = str(result.inserted_id)
        logger.info(f"Photo from user {user.id} saved to DB with ID: {link_id}")

        # Send simple confirmation FIRST
        await message.answer("✅ Материал получен и передан.")

        # Removed state clearing

        # Update user activity after successful submission
        await update_user_activity(user)
        logger.info(f"Updated activity for user {user.id} after photo submission.")

        # Notify master users (run asynchronously)
        await notify_master_users(bot=bot, link_data=link_data, link_id=link_id)

    except Exception as e:
        # Log the specific error after DB save
        logger.exception(f"Error processing photo for user {user.id} after DB save (link_id: {link_id}): {e}")
        # Attempt to notify user about the error, but confirmation was already sent
        try:
            await message.answer("Произошла ошибка при обработке вашего фото после сохранения. Администраторы уведомлены.")
        except Exception as notify_err:
            logger.error(f"Failed to notify user {user.id} about post-save error: {notify_err}")
        # Removed state clearing
        # Removed state clearing


# --- Removed Done Command Handler ---


# --- Document Message Handler (always active, filters for images) ---

@router.message(F.document) # Filter for document messages only
async def handle_link_document(message: types.Message, bot: Bot):
    """Handles document messages, processing them if they are images."""
    # Ignore documents that are not images
    if not message.document.mime_type or not message.document.mime_type.startswith('image/'):
        logger.debug(f"Ignoring non-image document (mime: {message.document.mime_type}) from user {message.from_user.id}")
        return # Exit handler if not an image document

    user = message.from_user
    doc = message.document
    file_id = doc.file_id
    caption = message.caption
    file_name = doc.file_name
    mime_type = doc.mime_type

    logger.info(f"Received image document from user {user.id}. File ID: {file_id}, Name: {file_name}, Mime: {mime_type}, Caption: '{caption[:50] if caption else ''}...'")

    # Silent ban check
    try:
        if await is_user_banned(user.id):
            await message.answer("✅ Материал получен и передан.")
            return
    except Exception:
        pass

    # Prepare data for DB
    link_data = LinkDB(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        telegram_file_id=file_id, # Store document file_id as telegram_file_id
        caption=caption,
        content_type='photo', # Treat image documents as photos for consistency
        file_name=file_name,  # Store original file name
        mime_type=mime_type   # Store mime type
    )

    # Save to MongoDB
    try:
        db = get_db()
        result = await db.links.insert_one(link_data.model_dump(by_alias=True))
        link_id = str(result.inserted_id)
        logger.info(f"Image document from user {user.id} saved to DB with ID: {link_id}")

        # Send simple confirmation FIRST
        await message.answer("✅ Материал получен и передан.")

        # Update user activity after successful submission
        await update_user_activity(user)
        logger.info(f"Updated activity for user {user.id} after image document submission.")

        # Notify master users (run asynchronously)
        # notify_master_users already handles content_type='photo'
        await notify_master_users(bot=bot, link_data=link_data, link_id=link_id)

    except Exception as e:
        # Log the specific error after DB save
        logger.exception(f"Error processing image document for user {user.id} after DB save (link_id: {link_id}): {e}")
        # Attempt to notify user about the error, but confirmation was already sent
        try:
            await message.answer("Произошла ошибка при обработке вашего материала после сохранения. Администраторы уведомлены.")
        except Exception as notify_err:
            logger.error(f"Failed to notify user {user.id} about post-save error: {notify_err}")
        # No state to clear


# --- Other content types are ignored by default ---
