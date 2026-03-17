import logging
import json
from typing import Optional, Literal, Dict, Any
from datetime import datetime
from bson import ObjectId

# Import shared components
from shared.db import get_applications_collection
from shared.types.enums import ApplicationStatus
from web.redis_client import publish_message # Assuming redis client is set up here
from web.config import settings # Web specific settings for queue name

logger = logging.getLogger(__name__)

async def _update_application_in_db(
    application_oid: ObjectId,
    status: ApplicationStatus,
    moderator_type: Literal["manual", "auto"],
    comment: Optional[str] = None,
    auto_moderation_result: Optional[Dict[str, Any]] = None
) -> bool:
    """Internal helper to update application fields in MongoDB."""
    collection = get_applications_collection()
    update_data = {
        "status": status.value,
        "moderated_at": datetime.utcnow(),
        "moderation_type": moderator_type,
        "moderation_comment": comment,
        "auto_moderation_result": auto_moderation_result
    }
    # Clean up fields based on status/type
    if status == ApplicationStatus.APPROVED:
        update_data["moderation_comment"] = None # Clear comment on approval

    if moderator_type == "manual":
         update_data["auto_moderation_result"] = None # Clear auto result if manual action

    result = await collection.update_one(
        {"_id": application_oid},
        {"$set": update_data}
    )
    return result.modified_count > 0 or result.matched_count > 0 # Return True if matched or modified

async def _publish_update_event(application_id: str, user_id: int, status: ApplicationStatus, comment: Optional[str]):
    """Internal helper to publish update event to Redis."""
    message_data = {
        "application_id": application_id,
        "user_id": user_id,
        "status": status.value,
    }
    # Include comment only for rejection
    if status == ApplicationStatus.REJECTED and comment:
        message_data["moderation_comment"] = comment

    try:
        await publish_message(settings.redis_queue_name, json.dumps(message_data))
        logger.info(f"Published {status.value} event for application {application_id} to Redis queue '{settings.redis_queue_name}'.")
    except Exception as e:
        logger.exception(f"Failed to publish event for application {application_id} to Redis: {e}")
        # Decide how to handle publish failure - maybe retry later?

async def approve_application(
    application_id_str: str,
    moderator_type: Literal["manual", "auto"],
    auto_moderation_result: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Approves an application: updates DB status and publishes event.

    Returns:
        True if the application was found and processed, False otherwise.
    """
    collection = get_applications_collection()
    try:
        application_oid = ObjectId(application_id_str)
    except Exception:
        logger.error(f"Invalid application ID format for approval: {application_id_str}")
        return False

    # Fetch user_id before updating, needed for notification
    application_doc = await collection.find_one({"_id": application_oid}, {"user_id": 1})
    if not application_doc:
        logger.warning(f"Application {application_id_str} not found for approval.")
        return False

    # Update DB
    updated = await _update_application_in_db(
        application_oid=application_oid,
        status=ApplicationStatus.APPROVED,
        moderator_type=moderator_type,
        auto_moderation_result=auto_moderation_result
    )

    if updated:
        logger.info(f"Application {application_id_str} approved ({moderator_type}).")
        # Publish event for bot notification
        await _publish_update_event(
            application_id=application_id_str,
            user_id=application_doc["user_id"],
            status=ApplicationStatus.APPROVED,
            comment=None
        )
        return True
    else:
        # This might happen if the document existed but wasn't modified (e.g., already approved)
        logger.warning(f"Application {application_id_str} was found but not modified during approval.")
        # Consider if we should still publish event if already approved? For now, only if modified.
        return False # Or True if "already approved" is considered success

async def reject_application(
    application_id_str: str,
    reason: str,
    moderator_type: Literal["manual", "auto"],
    auto_moderation_result: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Rejects an application: updates DB status with reason and publishes event.

    Returns:
        True if the application was found and processed, False otherwise.
    """
    collection = get_applications_collection()
    try:
        application_oid = ObjectId(application_id_str)
    except Exception:
        logger.error(f"Invalid application ID format for rejection: {application_id_str}")
        return False

    # Fetch user_id before updating
    application_doc = await collection.find_one({"_id": application_oid}, {"user_id": 1})
    if not application_doc:
        logger.warning(f"Application {application_id_str} not found for rejection.")
        return False

    # Update DB
    updated = await _update_application_in_db(
        application_oid=application_oid,
        status=ApplicationStatus.REJECTED,
        moderator_type=moderator_type,
        comment=reason,
        auto_moderation_result=auto_moderation_result
    )

    if updated:
        logger.info(f"Application {application_id_str} rejected ({moderator_type}). Reason: {reason}")
        # Publish event for bot notification
        await _publish_update_event(
            application_id=application_id_str,
            user_id=application_doc["user_id"],
            status=ApplicationStatus.REJECTED,
            comment=reason
        )
        return True
    else:
        logger.warning(f"Application {application_id_str} was found but not modified during rejection.")
        return False # Or True if "already rejected" is considered success
