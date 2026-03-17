import logging
from typing import List, Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse # Added RedirectResponse
from fastapi.templating import Jinja2Templates
from pymongo.database import Database
from aiogram import Bot # Added Bot
from aiogram.exceptions import TelegramAPIError # Added TelegramAPIError

# Import shared resources and models
from shared.db import get_db, get_banned_users, ban_user
from shared.models import LinkDB # Import the new model
from shared.config import settings # Added settings import
from ..auth import authenticate_moderator # Correct import for authentication

logger = logging.getLogger(__name__)

# Router setup
router = APIRouter(
    tags=["Links"], # Tag for API docs
    dependencies=[Depends(authenticate_moderator)] # Use the correct dependency
)

# Templates directory (relative to WORKDIR /app inside container)
templates = Jinja2Templates(directory="web/templates")

@router.get("/", response_class=HTMLResponse, name="list_links") # Changed path to root for this router
async def get_links_page(request: Request, db: Database = Depends(get_db), username: str = Depends(authenticate_moderator)): # Added username dependency for consistency, though not strictly needed here
    """Serves the HTML page displaying the list of submitted links."""
    try:
        # Fetch all links from the 'links' collection, sort by submission time descending
        links_cursor = db.links.find().sort("submitted_at", -1)
        links_list = []
        async for link_doc in links_cursor:
            # Convert MongoDB ObjectId to string if necessary, or handle directly in template
            # link_doc["_id"] = str(link_doc["_id"]) # Example if needed
            try:
                # Validate data with Pydantic model (optional but good practice)
                link_model = LinkDB(**link_doc)
                links_list.append(link_model)
            except Exception as e:
                logger.error(f"Error validating link data from DB: {link_doc}. Error: {e}")
                # Decide how to handle invalid data - skip or show with error? Skipping for now.
                continue

        # Load banned users to mark actions in UI
        banned = await get_banned_users()
        banned_ids = {bu.user_id for bu in banned}

        logger.info(f"Retrieved {len(links_list)} links from DB. Banned users: {len(banned_ids)}")

        return templates.TemplateResponse(
            "links.html", # New template name
            {
                "request": request,
                "links": links_list, # Pass the list of LinkDB objects
                "banned_ids": banned_ids,
                "page_title": "Присланные материалы" # Set page title
            }
        )
    except Exception as e:
        logger.exception("Error fetching or rendering links page.")
        # Consider returning an error response or a simpler error page
        raise HTTPException(status_code=500, detail="Internal server error fetching links.")

# --- Ban user endpoint ---

@router.post("/links/ban/{user_id}", name="ban_user")
async def ban_user_endpoint(user_id: int, moderator_username: str = Depends(authenticate_moderator)):
    """Bans a user by Telegram ID and redirects back to the links page."""
    try:
        success = await ban_user(user_id=user_id, reason=None, banned_by=moderator_username)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to ban user.")
        return RedirectResponse(url=router.url_path_for("list_links"), status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error banning user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error banning user.")

# --- New Endpoint to get file URL ---
@router.get("/file/{file_id}", response_class=RedirectResponse, name="get_telegram_file")
async def get_telegram_file(file_id: str):
    """
    Gets a temporary file download URL from Telegram and redirects the user.
    """
    bot_token = settings.telegram_bot_token
    if not bot_token or bot_token == "DEFINE_ME":
        logger.error("Telegram bot token is not configured in settings.")
        raise HTTPException(status_code=500, detail="Bot token not configured.")

    bot = Bot(token=bot_token)
    try:
        logger.debug(f"Attempting to get file info for file_id: {file_id}")
        file_info = await bot.get_file(file_id)
        if not file_info.file_path:
             logger.error(f"No file_path received from Telegram for file_id: {file_id}")
             raise HTTPException(status_code=404, detail="File path not found from Telegram.")

        # Construct the download URL using the bot token and file path
        # Note: This URL is temporary and might expire.
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_info.file_path}"
        logger.debug(f"Redirecting to Telegram file URL for file_id: {file_id}")
        return RedirectResponse(url=download_url, status_code=307) # Use 307 Temporary Redirect

    except TelegramAPIError as e:
        logger.error(f"Telegram API error getting file info for file_id {file_id}: {e}")
        if "file is too big" in str(e):
             raise HTTPException(status_code=400, detail="File is too big to download via API.")
        elif "FILE_ID_INVALID" in str(e) or "file not found" in str(e).lower():
             raise HTTPException(status_code=404, detail="File not found or invalid file ID.")
        else:
             raise HTTPException(status_code=502, detail=f"Telegram API error: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error getting file info for file_id {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error getting file URL.")
    finally:
        # Ensure the bot session is closed to prevent resource leaks
        await bot.session.close()
        logger.debug(f"Closed bot session for file_id: {file_id}")
