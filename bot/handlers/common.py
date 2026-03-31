import logging

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BotCommand

from bot.crypto_exchange_bot import REPLY_MENU_BUTTONS, build_reply_main_menu_keyboard
from bot.redis_client import increment_window_counter, publish_message
from bot.states import SupportStates
from shared import db
from shared.config import settings
from shared.models import MaterialDB, SupportMessageDB
from shared.types.enums import MaterialContentType

logger = logging.getLogger(__name__)
router = Router(name="common_handlers")


async def _apply_message_rate_limit(user_id: int) -> bool:
    current = await increment_window_counter(f"rate_limit:messages:{user_id}", 60)
    return current <= 10


async def _ensure_known_user(message: types.Message) -> None:
    await db.ensure_exchange_user(
        telegram_user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )


async def _enqueue_manager_notification(payload: dict) -> None:
    await publish_message(settings.notify_managers_queue_name, payload)


async def _save_material(
    message: types.Message,
    content_type: MaterialContentType,
    text: str | None = None,
    file_id: str | None = None,
    file_name: str | None = None,
    mime_type: str | None = None,
) -> str:
    material = MaterialDB(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        content_type=content_type,
        text=text,
        file_id=file_id,
        file_name=file_name,
        mime_type=mime_type,
    )
    return await db.create_material(material)


async def _store_generic_material(
    message: types.Message,
    content_type: MaterialContentType,
    text: str | None = None,
    file_id: str | None = None,
    file_name: str | None = None,
    mime_type: str | None = None,
) -> None:
    await _ensure_known_user(message)
    material_id = await _save_material(
        message=message,
        content_type=content_type,
        text=text,
        file_id=file_id,
        file_name=file_name,
        mime_type=mime_type,
    )
    await _enqueue_manager_notification(
        {
            "type": "notify_managers",
            "event": "material_received",
            "material_id": material_id,
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "content_type": content_type.value,
            "text": text,
            "file_id": file_id,
            "file_name": file_name,
            "mime_type": mime_type,
        }
    )


async def _store_support_message(
    message: types.Message,
    text: str,
    has_attachment: bool,
    attachment_type: MaterialContentType | None = None,
    file_id: str | None = None,
    file_name: str | None = None,
    mime_type: str | None = None,
) -> None:
    await _ensure_known_user(message)
    support_message = SupportMessageDB(
        user_id=message.from_user.id,
        username=message.from_user.username,
        text=text,
        has_attachment=has_attachment,
    )
    support_id = await db.create_support_message(support_message)
    material_id = None
    if attachment_type is not None or text:
        material_id = await _save_material(
            message=message,
            content_type=attachment_type or MaterialContentType.TEXT,
            text=text,
            file_id=file_id,
            file_name=file_name,
            mime_type=mime_type,
        )
    await _enqueue_manager_notification(
        {
            "type": "notify_managers",
            "event": "support_message",
            "support_id": support_id,
            "material_id": material_id,
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "text": text,
            "has_attachment": has_attachment,
            "content_type": attachment_type.value if attachment_type else MaterialContentType.TEXT.value,
            "file_id": file_id,
            "file_name": file_name,
            "mime_type": mime_type,
        }
    )


async def set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="menu", description="Открыть главное меню"),
        BotCommand(command="exchange", description="Создать заявку на обмен"),
        BotCommand(command="rates", description="Показать демо-курсы"),
        BotCommand(command="orders", description="Показать мои заявки"),
        BotCommand(command="profile", description="Открыть профиль"),
        BotCommand(command="support", description="Написать в поддержку"),
        BotCommand(command="broadcast", description="Рассылка для админа"),
        BotCommand(command="cancel", description="Отменить текущий сценарий"),
        BotCommand(command="stop", description="Удалить локальный профиль"),
    ]
    await bot.set_my_commands(commands)


@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await _ensure_known_user(message)
    user_name = message.from_user.first_name or message.from_user.full_name or "пользователь"
    await message.answer(
        (
            f"👋 Здравствуйте, {user_name}!\n\n"
            "Это демо-версия бота криптообменника для юридических лиц.\n\n"
            "Здесь вы можете:\n"
            "• Оформить заявку на обмен\n"
            "• Посмотреть актуальные курсы\n"
            "• Отследить статус заявок\n"
            "• Связаться с поддержкой\n\n"
            "Все операции демонстрационные и не являются реальными сделками."
        ),
        reply_markup=build_reply_main_menu_keyboard(),
    )


@router.message(Command("stop"))
async def handle_stop(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    deleted = await db.delete_exchange_user_data(message.from_user.id)
    if deleted:
        await message.answer("Ваш профиль удалён. Чтобы начать заново, используйте /start.")
        return
    await message.answer("Профиль не найден. Чтобы начать работу, используйте /start.")


@router.message(Command("broadcast"))
async def handle_broadcast(message: types.Message, bot: Bot) -> None:
    if message.from_user.id not in settings.master_user_ids_list:
        await message.answer("Команда доступна только администраторам демо.")
        return
    _, _, broadcast_text = (message.text or "").partition(" ")
    if not broadcast_text.strip():
        await message.answer("Использование: /broadcast <message>")
        return

    chat_ids = await db.get_all_known_user_ids()
    sent_count = 0
    failed_count = 0
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=broadcast_text)
            sent_count += 1
        except TelegramAPIError:
            logger.exception("Failed to broadcast to chat %s", chat_id)
            failed_count += 1
    await message.answer(f"Рассылка завершена. Отправлено: {sent_count}, ошибок: {failed_count}.")


@router.message(StateFilter(SupportStates.waiting_message), F.text)
async def handle_support_text(message: types.Message, state: FSMContext) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите текст сообщения для поддержки.")
        return
    if len(text) > 4096:
        await message.answer("Сообщение слишком длинное. Максимум 4096 символов.")
        return
    await _store_support_message(message, text=text, has_attachment=False)
    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено!\n\nВаше обращение зарегистрировано.\nМенеджер свяжется с вами в ближайшее время.",
        reply_markup=build_reply_main_menu_keyboard(),
    )


@router.message(StateFilter(SupportStates.waiting_message), F.photo)
async def handle_support_photo(message: types.Message, state: FSMContext) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > 10 * 1024 * 1024:
        await message.answer("Файл слишком большой. Максимум 10 MB.")
        return
    text = (message.caption or "").strip()
    await _store_support_message(
        message,
        text=text,
        has_attachment=True,
        attachment_type=MaterialContentType.PHOTO,
        file_id=photo.file_id,
    )
    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено!\n\nВаше обращение зарегистрировано.\nМенеджер свяжется с вами в ближайшее время.",
        reply_markup=build_reply_main_menu_keyboard(),
    )


@router.message(StateFilter(SupportStates.waiting_message), F.document)
async def handle_support_document(message: types.Message, state: FSMContext) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    document = message.document
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        await message.answer("Файл слишком большой. Максимум 10 MB.")
        return
    text = (message.caption or "").strip()
    await _store_support_message(
        message,
        text=text,
        has_attachment=True,
        attachment_type=MaterialContentType.DOCUMENT,
        file_id=document.file_id,
        file_name=document.file_name,
        mime_type=document.mime_type,
    )
    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено!\n\nВаше обращение зарегистрировано.\nМенеджер свяжется с вами в ближайшее время.",
        reply_markup=build_reply_main_menu_keyboard(),
    )


@router.message(StateFilter(None), F.text & ~F.text.in_(REPLY_MENU_BUTTONS) & ~F.text.startswith("/"))
async def handle_generic_text(message: types.Message) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    if await db.is_user_banned(message.from_user.id):
        await message.answer("✅ Материал получен и передан.")
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пожалуйста, отправьте текст сообщения.")
        return
    if len(text) > 4096:
        await message.answer("Сообщение слишком длинное. Максимум 4096 символов.")
        return
    await _store_generic_material(message, MaterialContentType.TEXT, text=text)
    await message.answer("✅ Материал получен и передан.")


@router.message(StateFilter(None), F.photo)
async def handle_generic_photo(message: types.Message) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    if await db.is_user_banned(message.from_user.id):
        await message.answer("✅ Материал получен и передан.")
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > 10 * 1024 * 1024:
        await message.answer("Файл слишком большой. Максимум 10 MB.")
        return
    await _store_generic_material(
        message,
        MaterialContentType.PHOTO,
        text=(message.caption or "").strip(),
        file_id=photo.file_id,
    )
    await message.answer("✅ Материал получен и передан.")


@router.message(StateFilter(None), F.document)
async def handle_generic_document(message: types.Message) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    if await db.is_user_banned(message.from_user.id):
        await message.answer("✅ Материал получен и передан.")
        return
    document = message.document
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        await message.answer("Файл слишком большой. Максимум 10 MB.")
        return
    await _store_generic_material(
        message,
        MaterialContentType.DOCUMENT,
        text=(message.caption or "").strip(),
        file_id=document.file_id,
        file_name=document.file_name,
        mime_type=document.mime_type,
    )
    await message.answer("✅ Материал получен и передан.")
