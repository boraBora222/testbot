import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
# Removed MemoryStorage import as FSM is not used for submission
# from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# Import local modules
from .config import settings
# Import handlers (questionnaire is disabled)
from .handlers import common #, questionnaire
# Import common helper functions
from .handlers.common import set_bot_commands
# Import Redis client functions
from .redis_client import get_redis_pool, close_redis_pool
# Import the specific queue consumer needed
from .queue_consumer import listen_broadcast_messages # Import the broadcast listener
# from .queue_consumer import listen_application_updates # Keep application listener commented out
from shared import db # Import shared DB functions

# Configure logging
# TODO: Configure logging more robustly (e.g., using logging.config.dictConfig)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    """Actions to perform on bot startup."""
    logger.info("Starting bot...")
    # Connect to Database
    await db.connect_db()
    # Set bot commands
    await set_bot_commands(bot)
    # Initialize Redis pool
    get_redis_pool()
    logger.info("Redis pool initialized.")
    # Start the broadcast message listener
    asyncio.create_task(listen_broadcast_messages(bot))
    logger.info("Broadcast message queue listener started.")
    # Keep application listener commented out
    # asyncio.create_task(listen_application_updates(bot))
    # logger.info("Application update queue listener started.")

async def on_shutdown(bot: Bot):
    """Actions to perform on bot shutdown."""
    logger.info("Stopping bot...")
    # Close database connection
    await db.disconnect_db()
    # Close Redis pool
    await close_redis_pool()
    # Close the bot's session to prevent dangling connections
    await bot.session.close()
    logger.info("Bot stopped.")

async def main() -> None:
    """Main function to initialize and run the bot."""
    # Ensure essential settings are present
    if not settings.telegram_bot_token or settings.telegram_bot_token == "DEFINE_ME":
        logger.critical("TELEGRAM_BOT_TOKEN is not defined in settings. Exiting.")
        sys.exit(1)
    if not settings.mongo_uri:
        logger.critical("MONGO_URI is not defined in settings. Exiting.")
        sys.exit(1)
    # Add check for Redis settings if critical
    # if not settings.redis_host:
    #     logger.critical("REDIS_HOST is not defined...")
    #     sys.exit(1)
    
    # Initialize Bot instance with default parse mode which will be passed to all API calls
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    # Initialize Dispatcher without storage if FSM is not needed
    # If other parts might use FSM later, keep MemoryStorage or switch to RedisStorage
    # storage = MemoryStorage()
    # dp = Dispatcher(storage=storage)
    dp = Dispatcher() # Initialize without storage

    # Register startup and shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Register routers/handlers
    dp.include_router(common.router)
    # dp.include_router(questionnaire.router) # Questionnaire router is disabled
    # Include other routers as needed

    # Start polling
    # await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    # It's generally recommended to remove startup/shutdown logic from start_polling
    # and handle it via the registered handlers above.
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot polling interrupted.")
