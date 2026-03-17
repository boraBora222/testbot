import logging
from typing import Optional, List
import pymongo # Import pymongo for index constants

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import ObjectId # Import ObjectId
from datetime import datetime # Import datetime

# Import settings from bot config (assuming shared access is okay for this structure)
# Alternatively, pass settings explicitly or use a shared config loader
# TODO: Refactor this later to avoid direct dependency on bot.config if web uses its own
# from bot.config import settings
# Import the shared application settings
from shared.config import settings

# Import models and enums
from shared.models import ApplicationDB, BannedUser
from shared.types.enums import ApplicationStatus

logger = logging.getLogger(__name__)

# Global variable to hold the MongoDB client instance
# Consider dependency injection for larger applications
_mongo_client: Optional[AsyncIOMotorClient] = None

def get_db() -> AsyncIOMotorDatabase:
    """Returns the application's MongoDB database instance."""
    if not _mongo_client:
        # This should ideally not happen if connect_db is called at startup
        logger.error("MongoDB client is not initialized. Call connect_db() first.")
        raise RuntimeError("Database client not initialized.")
    # Use shared settings now
    if not settings or not settings.mongo_db_name:
        logger.error("MongoDB database name is not configured in shared settings.")
        raise RuntimeError("Database name not configured.")

    return _mongo_client[settings.mongo_db_name]

def get_applications_collection():
    """Returns the collection for user applications."""
    db = get_db()
    return db["applications"] # Standard collection for applications

def get_usage_stats_collection():
    """Returns the collection for daily usage statistics."""
    db = get_db()
    return db["daily_usage_stats"] # Collection for LLM usage tracking

def get_banned_users_collection():
    """Returns the collection for banned users."""
    db = get_db()
    return db["banned_users"]

async def connect_db():
    """Establishes the connection to the MongoDB database."""
    global _mongo_client
    # Use shared settings now
    if not settings or not settings.mongo_uri:
        logger.error("MONGO_URI is not configured in shared settings. Cannot connect to database.")
        return # Or raise an error

    if _mongo_client:
        logger.warning("MongoDB client already initialized.")
        return

    logger.info(f"Connecting to MongoDB...") # Avoid logging full URI
    try:
        _mongo_client = AsyncIOMotorClient(settings.mongo_uri)
        # The ismaster command is cheap and does not require auth.
        await _mongo_client.admin.command('ismaster')
        logger.info("Successfully connected to MongoDB.")

        # Ensure indexes are created after successful connection
        try:
            db = get_db()
            # Create unique index on user_id for bot_users collection
            await db.bot_users.create_index([("user_id", pymongo.ASCENDING)], unique=True)
            logger.info("Ensured unique index on user_id in bot_users collection.")
            # Create unique index on user_id for banned_users collection
            await db.banned_users.create_index([("user_id", pymongo.ASCENDING)], unique=True)
            logger.info("Ensured unique index on user_id in banned_users collection.")
            # Add other index creations here if needed (e.g., for links, applications)
            # await db.links.create_index([("submitted_at", pymongo.DESCENDING)])
            # await db.applications.create_index([("submitted_at", pymongo.DESCENDING)])
            # await db.applications.create_index([("status", pymongo.ASCENDING)])

        except Exception as index_e:
            logger.exception(f"Failed to create indexes: {index_e}")
            # Decide if this should prevent the app from starting
            # For now, just log the error.

    except Exception as e:
        logger.exception(f"Failed to connect to MongoDB: {e}")
        _mongo_client = None # Reset client on failure
        # Depending on the application needs, you might want to raise the exception
        # raise

async def disconnect_db():
    """Closes the MongoDB connection."""
    global _mongo_client
    if _mongo_client:
        logger.info("Disconnecting from MongoDB...")
        _mongo_client.close()
        _mongo_client = None
        logger.info("Successfully disconnected from MongoDB.")
    else:
        logger.warning("MongoDB client is not initialized, cannot disconnect.")

# --- New functions for Web API ---

async def get_applications_by_status(status: ApplicationStatus) -> list[dict]:
    """Fetches applications from MongoDB based on their status, returning raw dicts including _id."""
    collection = get_applications_collection()
    applications_cursor = collection.find({"status": status.value})
    applications_list = []
    async for app_dict in applications_cursor:
        # Convert ObjectId to string before returning
        if "_id" in app_dict and isinstance(app_dict["_id"], ObjectId):
             app_dict["_id"] = str(app_dict["_id"])
        else:
            # Handle case where _id might be missing or not an ObjectId (shouldn't happen)
            logger.warning(f"Document missing or has invalid _id: {app_dict.get('_id')}")
            # Assign a placeholder or skip? For now, let Pydantic handle validation later.
            pass # Or explicitly set app_dict["_id"] = None if ApplicationResponse allows Optional id

        # Pydantic validation will happen in the router based on ApplicationResponse
        applications_list.append(app_dict)
        
        # Old code returning ApplicationDB instances:
        # try:
        #     applications_list.append(ApplicationDB(**app_dict))
        # except Exception as e:
        #     logger.error(f"Error validating application data from DB: {app_dict}, Error: {e}")
        #     continue 
    return applications_list

async def get_all_applications(sort_field: str = "submitted_at", sort_order: int = -1) -> list[dict]:
    """Fetches all applications from MongoDB, sorted, returning raw dicts including _id."""
    collection = get_applications_collection()
    # Use pymongo constants for sort order if preferred: from pymongo import DESCENDING, ASCENDING
    applications_cursor = collection.find({}).sort(sort_field, sort_order)
    applications_list = []
    async for app_dict in applications_cursor:
        # Convert ObjectId to string before returning
        if "_id" in app_dict and isinstance(app_dict["_id"], ObjectId):
             app_dict["_id"] = str(app_dict["_id"])
        else:
            logger.warning(f"Document missing or has invalid _id: {app_dict.get('_id')}")
            pass # Let Pydantic handle validation later

        applications_list.append(app_dict)
    return applications_list

async def update_application_status(
    application_id_str: str,
    status: ApplicationStatus,
    comment: Optional[str] = None
) -> bool:
    """Updates the status and optionally the moderation comment of an application."""
    collection = get_applications_collection()
    try:
        application_oid = ObjectId(application_id_str)
    except Exception:
        logger.error(f"Invalid application ID format: {application_id_str}")
        return False

    update_data = {
        "status": status.value,
        "moderated_at": datetime.utcnow()
    }
    if comment is not None:
        update_data["moderation_comment"] = comment
    elif status == ApplicationStatus.APPROVED: # Clear comment if approved
         update_data["moderation_comment"] = None

    result = await collection.update_one(
        {"_id": application_oid},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        logger.warning(f"Application with ID {application_id_str} not found for update.")
        return False
    if result.modified_count == 0:
        # This might happen if the status is already set to the target value
        logger.warning(f"Application {application_id_str} status was not modified (already {status.value}?).")
        # Consider returning True here as the desired state is achieved

    logger.info(f"Updated application {application_id_str} status to {status.value}")
    return True

# --- Function to mark notification status ---

async def set_application_notified(
    application_id_str: str,
    error: Optional[str] = None
) -> bool:
    """Marks an application as notified, optionally recording an error message."""
    collection = get_applications_collection()
    try:
        application_oid = ObjectId(application_id_str)
    except Exception:
        logger.error(f"Invalid application ID format for setting notified status: {application_id_str}")
        return False

    update_data = {
        "notified": True,
        "notification_error": error # Will set null if error is None
    }
    
    result = await collection.update_one(
        {"_id": application_oid},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        logger.warning(f"Application with ID {application_id_str} not found for setting notified status.")
        return False
    
    if error:
        logger.error(f"Marked application {application_id_str} as notified with error: {error}")
    else:
        logger.info(f"Marked application {application_id_str} as notified successfully.")

    return True

# --- Functions for LLM Usage Tracking ---

async def get_today_llm_usage() -> int:
    """Retrieves the total number of LLM characters used today."""
    collection = get_usage_stats_collection()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    usage_doc = await collection.find_one({"date": today_str})
    
    if usage_doc:
        return usage_doc.get("llm_characters_used", 0)
    else:
        return 0

async def increment_today_llm_usage(characters_count: int):
    """Increments the LLM character usage count for the current day."""
    if characters_count <= 0:
        return # No need to update if count is zero or negative

    collection = get_usage_stats_collection()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        await collection.update_one(
            {"date": today_str},
            {"$inc": {"llm_characters_used": characters_count}},
            upsert=True # Create the document if it doesn't exist for today
        )
        logger.debug(f"Incremented LLM usage for {today_str} by {characters_count}")
    except Exception as e:
        logger.exception(f"Failed to increment LLM usage for {today_str}: {e}")
        # Decide how to handle this error - maybe raise it?

# --- Banned users helpers ---

async def ban_user(user_id: int, reason: Optional[str] = None, banned_by: Optional[str] = None) -> bool:
    """Adds a user to the banned_users collection. Returns True if inserted or already banned."""
    collection = get_banned_users_collection()
    try:
        banned_user = BannedUser(user_id=user_id, reason=reason, banned_by=banned_by)
        await collection.update_one(
            {"user_id": user_id},
            {"$setOnInsert": banned_user.model_dump(by_alias=True)},
            upsert=True
        )
        return True
    except Exception as e:
        logger.exception(f"Failed to ban user {user_id}: {e}")
        return False

async def unban_user(user_id: int) -> bool:
    """Removes a user from the banned_users collection."""
    collection = get_banned_users_collection()
    try:
        result = await collection.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    except Exception as e:
        logger.exception(f"Failed to unban user {user_id}: {e}")
        return False

async def is_user_banned(user_id: int) -> bool:
    """Checks if a user is in the banned_users collection."""
    collection = get_banned_users_collection()
    try:
        doc = await collection.find_one({"user_id": user_id}, {"_id": 1})
        return doc is not None
    except Exception as e:
        logger.exception(f"Failed to check ban status for user {user_id}: {e}")
        return False

async def get_banned_users() -> List[BannedUser]:
    """Returns all banned users as BannedUser models."""
    collection = get_banned_users_collection()
    banned: List[BannedUser] = []
    try:
        cursor = collection.find({}).sort("banned_at", pymongo.DESCENDING)
        async for doc in cursor:
            try:
                banned.append(BannedUser(**doc))
            except Exception:
                continue
    except Exception as e:
        logger.exception(f"Failed to list banned users: {e}")
    return banned
