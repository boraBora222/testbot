import json
import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis

# Import shared modules
from ..auth import authenticate_moderator # Correct function name for authentication
from ..redis_client import get_redis_client # Import from the correct local module
# Assuming the key is defined centrally or known
# Ideally, this key would be shared via config or a shared constants file
BOT_CHATS_REDIS_KEY = "bot:known_chats"

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bot",
    tags=["Bot Info"],
    dependencies=[Depends(authenticate_moderator)] # Use correct dependency function
)

# --- Pydantic Models ---

class ChatInfo(BaseModel):
    """Represents information about a single chat known by the bot."""
    chat_id: int = Field(..., description="Telegram Chat ID")
    name: str = Field(..., description="Chat Title or User Full Name")

class BotChatsResponse(BaseModel):
    """Response model for the list of known bot chats."""
    chats: List[ChatInfo] = Field(..., description="List of chats the bot is aware of")

# --- API Endpoints ---

@router.get(
    "/chats",
    response_model=BotChatsResponse,
    summary="Get Known Bot Chats",
    description="Retrieves the list of chats (ID and name) that the bot has interacted with, as stored in Redis."
)
async def get_bot_chats():
    """
    Fetches the list of known chat IDs and names from Redis where the bot
    has received messages. The list is updated periodically by the bot.
    """
    redis: Redis = get_redis_client()
    known_chats: List[ChatInfo] = []
    try:
        chats_json = await redis.get(BOT_CHATS_REDIS_KEY)
        if chats_json:
            # Deserialize JSON from Redis
            # The bot saves it as { "chat_id_str": "name", ... }
            loaded_data: Dict[str, str] = json.loads(chats_json)
            # Convert back to list of ChatInfo objects
            known_chats = [
                ChatInfo(chat_id=int(chat_id_str), name=name)
                for chat_id_str, name in loaded_data.items()
            ]
            # Optional: Sort by name or ID
            known_chats.sort(key=lambda x: x.name.lower())
            logger.info(f"Retrieved {len(known_chats)} known chats from Redis for API request.")
        else:
            logger.info("No known chats found in Redis for API request.")
            # Return empty list, not an error

    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from Redis key '{BOT_CHATS_REDIS_KEY}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse chat data from storage."
        )
    except Exception as e:
        logger.exception(f"Failed to retrieve known chats from Redis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving chat data."
        )

    return BotChatsResponse(chats=known_chats)
