import logging
from typing import Optional

# Import shared settings
from shared.config import AppSettings

logger = logging.getLogger(__name__)

class BotSettings(AppSettings):
    """Loads bot-specific and shared application settings."""
    # Settings specific to the Telegram Bot
    telegram_bot_token: str

    # Target Telegram Chat ID (Group/Channel) where the bot is an admin
    # Optional, but needed for sending invite links
    target_chat_id: Optional[str] = None

    # model_config is inherited from AppSettings, including env_file loading

# Load settings
try:
    settings = BotSettings()
    logger.info("Bot application settings loaded successfully.")

    # Optional: Validate specific bot settings
    if not settings.target_chat_id:
        logger.warning("TARGET_CHAT_ID is not set in .env. Invite link functionality will be limited.")

    # Avoid logging sensitive info like tokens or full URIs in production
    # Log only non-sensitive shared settings and bot-specific ones (excluding token)
    log_dump = settings.model_dump(
        exclude={'telegram_bot_token', 'mongo_uri', 'google_gemini_api_key'}
    )
    logger.debug(f"Loaded bot settings: {log_dump}")

except Exception as e:
    logger.exception(f"Failed to load bot application settings: {e}")
    # Decide if the application should exit if config fails to load
    raise SystemExit(f"Configuration error: {e}") from e
