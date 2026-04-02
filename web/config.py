import logging
from typing import Literal

from pydantic import AliasChoices, Field

from shared.config import AppSettings

logger = logging.getLogger(__name__)


class WebSettings(AppSettings):
    """Loads web-specific and shared application settings."""

    web_app_host: str = "0.0.0.0"
    web_app_port: int = 8000

    # Moderator credentials remain separate from website user auth.
    moderator_username: str = Field(validation_alias=AliasChoices("WEB_USERNAME", "MODERATOR_USERNAME"))
    moderator_password: str = Field(validation_alias=AliasChoices("WEB_PASSWORD", "MODERATOR_PASSWORD"))

    # Session auth settings
    auth_cookie_name: str = "cryptodeal_session"
    auth_session_ttl_hours: int = 24
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_password_min_length: int = 8
    auth_verification_code_ttl_minutes: int = 10
    auth_reset_code_ttl_minutes: int = 10
    auth_verification_code_length: int = 6
    auth_reset_code_length: int = 6
    auth_max_code_attempts: int = 5

    # SMTP settings for upcoming verification/reset flows
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True


try:
    settings = WebSettings()
    logger.info("Web application settings loaded successfully.")
    log_dump = settings.model_dump(
        exclude={
            "mongo_uri",
            "moderator_password",
            "google_gemini_api_key",
            "telegram_bot_token",
            "smtp_password",
        }
    )
    logger.debug("Loaded web settings: %s", log_dump)
except Exception as exc:
    logger.exception("Failed to load web application settings: %s", exc)
    raise SystemExit(f"Configuration error: {exc}") from exc
