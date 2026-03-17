import asyncio
import json
import logging
from typing import Dict, Any

from aiogram import Dispatcher, types
from redis.asyncio import Redis

from .redis_client import get_redis_client
from .config import settings

logger = logging.getLogger(__name__)

# Ключ в Redis для хранения информации о чатах
REDIS_CHATS_KEY = "bot:known_chats"
# Интервал сохранения в Redis (в секундах)
SAVE_INTERVAL = 60 * 5 # Каждые 5 минут

# Словарь для хранения известных чатов в памяти {chat_id: chat_title}
known_chats: Dict[int, str] = {}

async def update_known_chat(message: types.Message):
    """
    Обновляет словарь известных чатов при получении сообщения.
    Вызывается как хендлер для всех типов сообщений.
    """
    chat_id = message.chat.id
    # Не обновляем, если чат уже известен (экономим ресурсы)
    # Можно убрать эту проверку, если нужно всегда обновлять название чата
    if chat_id not in known_chats:
        # Определяем имя: title для групп/каналов, full_name для личных чатов
        chat_name = message.chat.title
        if not chat_name:
            # Если title нет (личный чат), используем имя пользователя
            # Учитываем, что from_user может отсутствовать в некоторых редких случаях
            user = message.from_user
            chat_name = user.full_name if user else f"User {chat_id}" # Fallback name

        known_chats[chat_id] = chat_name
        logger.info(f"Discovered or updated chat: ID={chat_id}, Name='{chat_name}'")
        # Можно инициировать сохранение в Redis сразу после обнаружения нового чата,
        # но периодическое сохранение снижает нагрузку.

async def save_chats_to_redis_periodically():
    """
    Периодически сохраняет словарь known_chats в Redis.
    Запускается как фоновая задача asyncio.
    """
    redis: Redis = get_redis_client()
    logger.info(f"Starting periodic saving of known chats to Redis key '{REDIS_CHATS_KEY}' every {SAVE_INTERVAL}s")
    while True:
        await asyncio.sleep(SAVE_INTERVAL)
        if not known_chats:
            continue # Нечего сохранять

        try:
            # Копируем словарь перед сохранением на случай изменений во время операции
            chats_to_save = dict(known_chats)
            # Сериализуем в JSON для хранения в одной строке Redis
            # Преобразуем chat_id (int) в строку, т.к. JSON ключи должны быть строками
            chats_json = json.dumps({str(k): v for k, v in chats_to_save.items()})

            await redis.set(REDIS_CHATS_KEY, chats_json)
            logger.info(f"Saved {len(chats_to_save)} known chats to Redis.")
        except Exception as e:
            logger.exception(f"Failed to save known chats to Redis: {e}")

async def load_chats_from_redis():
    """
    Загружает список известных чатов из Redis при старте бота.
    """
    global known_chats
    redis: Redis = get_redis_client()
    try:
        chats_json = await redis.get(REDIS_CHATS_KEY)
        if chats_json:
            # Десериализуем JSON и преобразуем ключи обратно в int
            loaded_data = json.loads(chats_json)
            known_chats = {int(k): v for k, v in loaded_data.items()}
            logger.info(f"Loaded {len(known_chats)} known chats from Redis.")
        else:
            logger.info("No known chats found in Redis to load.")
    except Exception as e:
        logger.exception(f"Failed to load known chats from Redis: {e}")
        known_chats = {} # Начинаем с пустого словаря в случае ошибки

def register_chat_tracker_handlers(dp: Dispatcher):
    """
    Регистрирует хендлеры для отслеживания чатов.
    """
    # Регистрируем хендлер для всех типов сообщений, чтобы ловить активность в чатах
    # В Aiogram 3.x фильтры (как content_types) передаются иначе или не требуются для общего обработчика.
    # Регистрация без фильтров будет ловить все сообщения, не обработанные ранее.
    dp.message.register(update_known_chat)
    # Можно также добавить хендлеры на другие события, например, добавление бота в чат,
    # если aiogram предоставляет такие события в удобном виде.
    logger.info("Chat tracker message handler registered.")
