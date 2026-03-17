import logging
from shared.config import AppSettings # Import shared settings
from pydantic import Field, AliasChoices

logger = logging.getLogger(__name__)

class WebSettings(AppSettings):
    """Loads web-specific and shared application settings."""
    # Settings specific to the Web Interface
    web_app_host: str = "0.0.0.0"
    web_app_port: int = 8000

    # Moderator credentials for Basic Auth
    moderator_username: str = Field(validation_alias=AliasChoices("WEB_USERNAME", "MODERATOR_USERNAME"))
    moderator_password: str = Field(validation_alias=AliasChoices("WEB_PASSWORD", "MODERATOR_PASSWORD"))

    # model_config is inherited from AppSettings, including env_file loading

# Load settings
try:
    settings = WebSettings()
    logger.info("Web application settings loaded successfully.")

    # Avoid logging sensitive info like MONGO_URI or passwords in production
    log_dump = settings.model_dump(
        exclude={'mongo_uri', 'moderator_password', 'google_gemini_api_key', 'telegram_bot_token'}
    )
    logger.debug(f"Loaded web settings: {log_dump}")

except Exception as e:
    logger.exception(f"Failed to load web application settings: {e}")
    # Decide if the application should exit if config fails to load
    raise SystemExit(f"Configuration error: {e}") from e
