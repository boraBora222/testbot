import logging
from decimal import Decimal
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PositiveInt

logger = logging.getLogger(__name__)


class AppSettings(BaseSettings):
    """Loads all shared application settings from environment variables."""

    model_config = SettingsConfigDict(
        # env_file removed, settings are loaded directly from environment variables
        # provided by docker compose --env-file
        extra="ignore",
    )

    # MongoDB settings
    mongo_uri: str = "mongodb://mongo:27017/"
    mongo_db_name: str

    # Redis settings
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_queue_name: Optional[str] = None
    auto_moderation_queue_name: Optional[str] = None
    broadcast_queue_name: str = "reply_bot_broadcast_queue"
    order_status_queue_name: str = "bot:order_status"
    notify_managers_queue_name: str = "bot:notify_managers"

    # Web Admin settings for notifications
    web_base_url: str

    # Bot settings
    telegram_bot_token: str
    master_user_ids: str
    demo_mode: bool = True
    default_fee_percent: Decimal = Decimal("0.5")
    min_exchange_amount_rub: Decimal = Decimal("10000")
    max_exchange_amount_rub: Decimal = Decimal("10000000")
    fsm_timeout_minutes: PositiveInt = 30
    rates_usdt_rub: Decimal = Decimal("92.5000")
    rates_btc_rub: Decimal = Decimal("8500000.0000")
    rates_eth_rub: Decimal = Decimal("250000.0000")
    rates_usdt_btc: Decimal = Decimal("0.0000109")
    rates_btc_usdt: Decimal = Decimal("91743.1193")
    rates_eth_usdt: Decimal = Decimal("2702.7027")
    log_level: str = "INFO"

    # Google Gemini API settings (kept for compatibility; optional now)
    google_gemini_api_key: Optional[str] = None
    auto_moderation_daily_limit: PositiveInt = 1_000_000
    auto_moderation_prompt: str = Field(
        default=(
            "Analyze the following user application answers and decide if the user "
            "seems like a real person suitable for the community. Provide your decision "
            # Double the braces around the JSON example to treat them as literal braces
            "in JSON format: {{ \"decision\": \"approve\" or \"decline\", \"reason\": "
            "\"Your detailed reasoning here.\" }}. Application answers:\n{answers_text}"
        )
    )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def master_user_ids_list(self) -> list[int]:
        result: list[int] = []
        for raw_value in self.master_user_ids.split(","):
            candidate = raw_value.strip()
            if candidate.isdigit():
                result.append(int(candidate))
        return result


# Instantiate the settings
settings = AppSettings()

# Basic log to confirm loading
logger.debug(f"Shared App settings loaded: DB={settings.mongo_db_name}, Redis={settings.redis_host}:{settings.redis_port}")
