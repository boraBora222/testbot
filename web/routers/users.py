import logging
import json
from typing import List, Dict, Any

import pymongo # Import pymongo for sorting constants
from fastapi import APIRouter, Depends, Request, Form, HTTPException
# Import standard responses from fastapi.responses
from fastapi.responses import HTMLResponse, RedirectResponse
# Import Jinja2Templates from fastapi.templating
from fastapi.templating import Jinja2Templates

# Correct imports:
# auth is in the parent directory (web)
from ..auth import authenticate_moderator
# shared is a top-level package relative to the app root
from shared.db import get_db
from shared.models import BotUser # Import BotUser model for potential validation/typing
from shared.config import settings
# redis_client is in the parent directory (web)
from ..redis_client import publish_message
from shared.db import get_banned_users
from shared.db import is_user_banned

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Users & Broadcast"],
    dependencies=[Depends(authenticate_moderator)] # Use the correct dependency
)

# Re-add local templates instance, similar to links.py
templates = Jinja2Templates(directory="web/templates")

# --- Routes ---

@router.get("/users", response_class=HTMLResponse, name="get_users_page")
async def get_users_page(request: Request, db=Depends(get_db)):
    """Displays the page with all users who interacted with the bot and the broadcast form."""
    try:
        # Fetch all users from the bot_users collection
        # Sort by last_seen_at descending (most recent first)
        users_cursor = db.bot_users.find({}).sort("last_seen_at", pymongo.DESCENDING)
        # Convert cursor to list. We can potentially validate with BotUser model here if needed,
        # but for simplicity, we pass the raw dicts to the template for now.
        users_list = await users_cursor.to_list(length=None) # Get all users

        logger.info(f"Found {len(users_list)} users in the bot_users collection.")

        # Use the local templates instance to call TemplateResponse
        banned = await get_banned_users()
        banned_ids = {u.user_id for u in banned}

        return templates.TemplateResponse(
            "users.html",
            {"request": request, "users": users_list, "banned_ids": banned_ids}
        )
    except Exception as e:
        logger.exception("Error fetching users from bot_users collection.")
        # Optionally, render an error page or return an HTTP error
        # For now, render the page with an empty list and an error message
        # Use the local templates instance to call TemplateResponse
        return templates.TemplateResponse(
            "users.html",
            {"request": request, "users": [], "error": "Could not load users."}
        )

@router.post("/users/broadcast", name="broadcast_message")
async def handle_broadcast(
    request: Request,
    message: str = Form(...),
    db=Depends(get_db)
):
    """Handles the broadcast form submission, queues messages in Redis."""
    if not message or not message.strip():
        # Basic validation: prevent empty messages
        # Ideally, add feedback to the user on the page
        logger.warning("Broadcast attempt with empty message.")
        # Redirect back to the users page, maybe with an error query param?
        return RedirectResponse(url=router.url_path_for("get_users_page"), status_code=303)

    try:
        # Get distinct user IDs from the links collection
        # Similar aggregation as GET, but only need user_id
        pipeline = [
            {"$group": {"_id": "$user_id"}},
            {"$project": {"_id": 0, "user_id": "$_id"}}
        ]
        users_cursor = db.links.aggregate(pipeline)
        user_ids = [doc["user_id"] async for doc in users_cursor]

        if not user_ids:
            logger.warning("Broadcast attempt with no users found in links collection.")
            # Redirect back, maybe with a message?
            return RedirectResponse(url=router.url_path_for("get_users_page"), status_code=303)

        logger.info(f"Queueing broadcast message for {len(user_ids)} users.")

        # Queue tasks in Redis
        queued_count = 0
        failed_count = 0
        for user_id in user_ids:
            # Skip banned users
            try:
                if await is_user_banned(int(user_id)):
                    logger.info(f"Skipping broadcast enqueue for banned user {user_id}")
                    continue
            except Exception:
                pass
            task = {
                "type": "broadcast", # Add a type for potential future task differentiation
                "user_id": user_id,
                "text": message
            }
            try:
                # Ensure the queue name from settings is used
                await publish_message(settings.broadcast_queue_name, json.dumps(task))
                queued_count += 1
            except Exception as e:
                logger.error(f"Failed to queue broadcast task for user_id {user_id}: {e}")
                failed_count += 1

        logger.info(f"Broadcast queuing complete. Success: {queued_count}, Failed: {failed_count}")

        # Redirect back to the users page after queuing
        # Consider adding success/failure counts as query params for user feedback
        return RedirectResponse(url=router.url_path_for("get_users_page"), status_code=303) # Use 303 See Other for POST-redirect

    except Exception as e:
        logger.exception("Error during broadcast message handling.")
        # Redirect back with a generic error indicator?
        # Or raise HTTPException(status_code=500, detail="Internal server error during broadcast.")
        return RedirectResponse(url=router.url_path_for("get_users_page"), status_code=303)
