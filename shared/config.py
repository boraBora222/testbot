import logging
from typing import Optional # Import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PositiveInt

logger = logging.getLogger(__name__)

class AppSettings(BaseSettings):
    """Loads all shared application settings from environment variables."""
    model_config = SettingsConfigDict(
        # env_file removed, settings are loaded directly from environment variables
        # provided by docker compose --env-file
        extra='ignore' # Ignore extra fields loaded from environment
    )

    # MongoDB settings
    mongo_uri: str = "mongodb://mongo:27017/" # Default to Docker service name
    mongo_db_name: str # Database name (from .env)

    # Redis settings (provide sensible defaults for Docker network)
    redis_host: str = "redis" # Default to Docker service name
    redis_port: int = 6379 # Default Redis port
    redis_db: int = 0 # Can be overridden in .env
    redis_queue_name: Optional[str] = None # Queue for status updates (from .env) - Made optional as it might not be used now
    auto_moderation_queue_name: Optional[str] = None # Queue for auto-moderation (from .env) - Made optional
    broadcast_queue_name: str = "reply_bot_broadcast_queue" # Queue for broadcast messages

    # Web Admin settings for notifications
    web_base_url: str # Base URL for the web admin (from .env)

    # Ask Naboka specific settings
    telegram_bot_token: str # Bot token (needed by web for file proxy)
    master_user_ids: str # Comma-separated list of master user IDs (from .env)

    # Google Gemini API settings (kept for compatibility; optional now)
    google_gemini_api_key: Optional[str] = None # API Key (from .env)
    auto_moderation_daily_limit: PositiveInt = 1_000_000 # Default limit
    auto_moderation_prompt: str = Field(
        default=(
            "Analyze the following user application answers and decide if the user "
            "seems like a real person suitable for the community. Provide your decision "
            # Double the braces around the JSON example to treat them as literal braces
            "in JSON format: {{ \"decision\": \"approve\" or \"decline\", \"reason\": "
            "\"Your detailed reasoning here.\" }}. Application answers:\n{answers_text}" # Single braces for the actual placeholder
        )
    )

# Instantiate the settings
settings = AppSettings()

# Basic log to confirm loading
logger.debug(f"Shared App settings loaded: DB={settings.mongo_db_name}, Redis={settings.redis_host}:{settings.redis_port}")
