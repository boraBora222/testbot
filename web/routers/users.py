import logging
import json
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

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
from shared.db import (
    get_banned_users,
    get_limit_quota,
    is_user_banned,
    list_limit_quota_history,
    list_pending_whitelist_addresses,
    moderate_whitelist_address,
)
from shared.async_tracing import add_async_trace
from shared.config import settings
from shared.services.security_settings import update_limit_quota_with_audit
from shared.types.enums import VerificationLevel, WhitelistAddressStatus
# redis_client is in the parent directory (web)
from ..redis_client import publish_message

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Users & Broadcast"],
    dependencies=[Depends(authenticate_moderator)] # Use the correct dependency
)

# Re-add local templates instance, similar to links.py
templates = Jinja2Templates(directory="web/templates")


def _build_redirect_url(route_name: str, *, message: str | None = None, error: str | None = None) -> str:
    base_url = router.url_path_for(route_name)
    query_params: dict[str, str] = {}
    if message:
        query_params["message"] = message
    if error:
        query_params["error"] = error
    if not query_params:
        return base_url
    return f"{base_url}?{urlencode(query_params)}"


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _parse_positive_decimal(value: str, *, field_name: str) -> Decimal:
    try:
        decimal_value = Decimal(value.strip())
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"{field_name} must be a valid decimal value.") from exc
    if decimal_value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return decimal_value

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
            request=request,
            name="users.html",
            context={"request": request, "users": users_list, "banned_ids": banned_ids},
        )
    except Exception as e:
        logger.exception("Error fetching users from bot_users collection.")
        # Optionally, render an error page or return an HTTP error
        # For now, render the page with an empty list and an error message
        # Use the local templates instance to call TemplateResponse
        return templates.TemplateResponse(
            request=request,
            name="users.html",
            context={"request": request, "users": [], "error": "Could not load users."},
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
        exchange_user_ids = await db.users.distinct("telegram_user_id")
        legacy_user_ids = await db.bot_users.distinct("user_id")
        user_ids = sorted({int(user_id) for user_id in exchange_user_ids + legacy_user_ids if user_id is not None})

        if not user_ids:
            logger.warning("Broadcast attempt with no users found in user collections.")
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
                task = add_async_trace(
                    task,
                    producer="web.users.broadcast",
                    queue_name=settings.broadcast_queue_name,
                    event_name="broadcast",
                )
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


@router.get("/users/whitelist/pending", response_class=HTMLResponse, name="get_pending_whitelist_page")
async def get_pending_whitelist_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    db=Depends(get_db),
):
    try:
        pending_entries = await list_pending_whitelist_addresses()
        user_ids = sorted({int(entry["user_id"]) for entry in pending_entries})
        users_by_id: dict[int, dict[str, Any]] = {}
        if user_ids:
            async for user_doc in db.users.find({"telegram_user_id": {"$in": user_ids}}):
                users_by_id[int(user_doc["telegram_user_id"])] = user_doc

        return templates.TemplateResponse(
            request=request,
            name="whitelist_pending.html",
            context={
                "request": request,
                "entries": pending_entries,
                "users_by_id": users_by_id,
                "message": message,
                "error": error,
            },
        )
    except Exception:
        logger.exception("Error loading pending whitelist moderation page.")
        return templates.TemplateResponse(
            request=request,
            name="whitelist_pending.html",
            context={
                "request": request,
                "entries": [],
                "users_by_id": {},
                "error": error or "Could not load pending whitelist entries.",
                "message": message,
            },
        )


@router.post("/users/whitelist/{whitelist_id}/approve", name="approve_whitelist_entry")
async def approve_whitelist_entry(whitelist_id: str, moderator_username: str = Depends(authenticate_moderator)):
    try:
        updated_entry = await moderate_whitelist_address(
            whitelist_id,
            new_status=WhitelistAddressStatus.ACTIVE,
            verified_by=moderator_username,
        )
        if updated_entry is None:
            redirect_url = _build_redirect_url("get_pending_whitelist_page", error="Whitelist entry not found.")
        else:
            redirect_url = _build_redirect_url(
                "get_pending_whitelist_page",
                message=f"Whitelist entry {updated_entry['id']} approved.",
            )
    except ValueError as exc:
        redirect_url = _build_redirect_url("get_pending_whitelist_page", error=str(exc))
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/users/whitelist/{whitelist_id}/reject", name="reject_whitelist_entry")
async def reject_whitelist_entry(
    whitelist_id: str,
    reason: str = Form(...),
    moderator_username: str = Depends(authenticate_moderator),
):
    try:
        updated_entry = await moderate_whitelist_address(
            whitelist_id,
            new_status=WhitelistAddressStatus.REJECTED,
            verified_by=moderator_username,
            rejection_reason=reason,
        )
        if updated_entry is None:
            redirect_url = _build_redirect_url("get_pending_whitelist_page", error="Whitelist entry not found.")
        else:
            redirect_url = _build_redirect_url(
                "get_pending_whitelist_page",
                message=f"Whitelist entry {updated_entry['id']} rejected.",
            )
    except ValueError as exc:
        redirect_url = _build_redirect_url("get_pending_whitelist_page", error=str(exc))
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/users/limits", response_class=HTMLResponse, name="get_user_limits_page")
async def get_user_limits_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    db=Depends(get_db),
):
    try:
        users_cursor = db.users.find({}).sort("last_activity_at", pymongo.DESCENDING)
        users = await users_cursor.to_list(length=None)

        limit_rows: list[dict[str, Any]] = []
        for user in users:
            user_id = int(user["telegram_user_id"])
            quota = await get_limit_quota(user_id)
            limit_rows.append(
                {
                    "user": user,
                    "quota": quota,
                }
            )

        history = await list_limit_quota_history(limit=50)
        return templates.TemplateResponse(
            request=request,
            name="user_limits.html",
            context={
                "request": request,
                "rows": limit_rows,
                "history": history,
                "message": message,
                "error": error,
                "verification_levels": list(VerificationLevel),
                "format_decimal": _format_decimal,
            },
        )
    except Exception:
        logger.exception("Error loading user limits page.")
        return templates.TemplateResponse(
            request=request,
            name="user_limits.html",
            context={
                "request": request,
                "rows": [],
                "history": [],
                "message": message,
                "error": error or "Could not load user limits.",
                "verification_levels": list(VerificationLevel),
                "format_decimal": _format_decimal,
            },
        )


@router.post("/users/limits/{user_id}", name="save_user_limits")
async def save_user_limits(
    user_id: int,
    verification_level: str = Form(...),
    daily_limit: str = Form(...),
    monthly_limit: str = Form(...),
    reason: str = Form(...),
    moderator_username: str = Depends(authenticate_moderator),
    db=Depends(get_db),
):
    try:
        exchange_user = await db.users.find_one({"telegram_user_id": user_id}, {"telegram_user_id": 1})
        if exchange_user is None:
            raise ValueError("Exchange user not found.")

        saved_quota, history_rows = await update_limit_quota_with_audit(
            user_id=user_id,
            verification_level=VerificationLevel(verification_level),
            daily_limit=_parse_positive_decimal(daily_limit, field_name="Daily limit"),
            monthly_limit=_parse_positive_decimal(monthly_limit, field_name="Monthly limit"),
            reason=reason,
            changed_by=moderator_username,
        )
        if history_rows:
            redirect_url = _build_redirect_url(
                "get_user_limits_page",
                message=f"Saved limits for user {saved_quota.user_id}. {len(history_rows)} change(s) audited.",
            )
        else:
            redirect_url = _build_redirect_url(
                "get_user_limits_page",
                message=f"No limit changes detected for user {saved_quota.user_id}.",
            )
    except ValueError as exc:
        redirect_url = _build_redirect_url("get_user_limits_page", error=str(exc))
    return RedirectResponse(url=redirect_url, status_code=303)
