import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pymongo
from bson import ObjectId
from bson.decimal128 import Decimal128
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ReturnDocument

from shared.config import settings
from shared.models import (
    ApplicationDB,
    AuthSessionDB,
    BannedUser,
    BotUser,
    ExchangeUserDB,
    LinkDB,
    MaterialDB,
    OrderDB,
    SupportMessageDB,
    WebUserDB,
    WebsiteSubmissionDB,
)
from shared.types.enums import ApplicationStatus, MaterialContentType, OrderStatus

logger = logging.getLogger(__name__)

_mongo_client: Optional[AsyncIOMotorClient] = None
_ORDER_DECIMAL_FIELDS = ("amount", "rate", "fee_percent", "fee_amount", "receive_amount")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal128(value: Decimal) -> Decimal128:
    return Decimal128(str(value))


def _from_decimal128(value: object) -> Decimal:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _serialize_order(order: OrderDB) -> dict:
    payload = order.model_dump()
    for field_name in _ORDER_DECIMAL_FIELDS:
        payload[field_name] = _to_decimal128(payload[field_name])
    payload["exchange_type"] = order.exchange_type.value
    payload["status"] = order.status.value
    return payload


def _deserialize_order(document: dict) -> dict:
    serialized = dict(document)
    if "_id" in serialized:
        serialized["_id"] = str(serialized["_id"])
    for field_name in _ORDER_DECIMAL_FIELDS:
        serialized[field_name] = _from_decimal128(serialized[field_name])
    return serialized


def get_db() -> AsyncIOMotorDatabase:
    """Returns the application's MongoDB database instance."""
    if not _mongo_client:
        logger.error("MongoDB client is not initialized. Call connect_db() first.")
        raise RuntimeError("Database client not initialized.")
    if not settings.mongo_db_name:
        logger.error("MongoDB database name is not configured.")
        raise RuntimeError("Database name not configured.")
    return _mongo_client[settings.mongo_db_name]


def get_applications_collection():
    return get_db()["applications"]


def get_usage_stats_collection():
    return get_db()["daily_usage_stats"]


def get_banned_users_collection():
    return get_db()["banned_users"]


def get_website_submissions_collection():
    return get_db()["website_submissions"]


async def _ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    await database.bot_users.create_index([("user_id", pymongo.ASCENDING)], unique=True)
    await database.users.create_index([("telegram_user_id", pymongo.ASCENDING)], unique=True)
    await database.banned_users.create_index([("user_id", pymongo.ASCENDING)], unique=True)
    await database.links.create_index([("submitted_at", pymongo.DESCENDING)])
    await database.website_submissions.create_index([("created_at", pymongo.DESCENDING)])
    await database.website_submissions.create_index([("source", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
    await database.materials.create_index([("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
    await database.support_messages.create_index([("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
    await database.orders.create_index([("order_id", pymongo.ASCENDING)], unique=True)
    await database.orders.create_index([("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
    await database.orders.create_index([("status", pymongo.ASCENDING), ("updated_at", pymongo.DESCENDING)])


async def connect_db() -> None:
    """Establishes the connection to the MongoDB database."""
    global _mongo_client

    if _mongo_client:
        logger.info("MongoDB client already initialized.")
        return

    logger.info("Connecting to MongoDB.")
    try:
        _mongo_client = AsyncIOMotorClient(settings.mongo_uri)
        await _mongo_client.admin.command("ping")
        await _ensure_indexes(get_db())
        logger.info("Successfully connected to MongoDB.")
    except Exception as exc:
        logger.exception("Failed to connect to MongoDB.")
        _mongo_client = None
        raise RuntimeError("Failed to connect to MongoDB.") from exc


async def disconnect_db() -> None:
    """Closes the MongoDB connection."""
    global _mongo_client
    if not _mongo_client:
        return
    logger.info("Disconnecting from MongoDB.")
    _mongo_client.close()
    _mongo_client = None
    logger.info("Successfully disconnected from MongoDB.")


async def get_applications_by_status(status: ApplicationStatus) -> list[dict]:
    collection = get_applications_collection()
    applications: list[dict] = []
    async for app_dict in collection.find({"status": status.value}):
        if "_id" in app_dict and isinstance(app_dict["_id"], ObjectId):
            app_dict["_id"] = str(app_dict["_id"])
        applications.append(app_dict)
    return applications


async def get_all_applications(sort_field: str = "submitted_at", sort_order: int = -1) -> list[dict]:
    collection = get_applications_collection()
    applications: list[dict] = []
    async for app_dict in collection.find({}).sort(sort_field, sort_order):
        if "_id" in app_dict and isinstance(app_dict["_id"], ObjectId):
            app_dict["_id"] = str(app_dict["_id"])
        applications.append(app_dict)
    return applications


async def update_application_status(
    application_id_str: str,
    status: ApplicationStatus,
    comment: Optional[str] = None,
) -> bool:
    collection = get_applications_collection()
    try:
        application_oid = ObjectId(application_id_str)
    except InvalidId:
        logger.error("Invalid application ID format: %s", application_id_str)
        return False

    update_data = {
        "status": status.value,
        "moderated_at": datetime.utcnow(),
    }
    if comment is not None:
        update_data["moderation_comment"] = comment
    elif status == ApplicationStatus.APPROVED:
        update_data["moderation_comment"] = None

    result = await collection.update_one({"_id": application_oid}, {"$set": update_data})
    if result.matched_count == 0:
        logger.warning("Application not found for update: %s", application_id_str)
        return False

    logger.info("Updated application %s status to %s", application_id_str, status.value)
    return True


async def set_application_notified(application_id_str: str, error: Optional[str] = None) -> bool:
    collection = get_applications_collection()
    try:
        application_oid = ObjectId(application_id_str)
    except InvalidId:
        logger.error("Invalid application ID format for notification update: %s", application_id_str)
        return False

    result = await collection.update_one(
        {"_id": application_oid},
        {"$set": {"notified": True, "notification_error": error}},
    )
    if result.matched_count == 0:
        logger.warning("Application not found for notification update: %s", application_id_str)
        return False

    return True


async def get_today_llm_usage() -> int:
    collection = get_usage_stats_collection()
    usage_doc = await collection.find_one({"date": datetime.utcnow().strftime("%Y-%m-%d")})
    if usage_doc:
        return usage_doc.get("llm_characters_used", 0)
    return 0


async def increment_today_llm_usage(characters_count: int) -> None:
    if characters_count <= 0:
        return
    collection = get_usage_stats_collection()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    await collection.update_one(
        {"date": today_str},
        {"$inc": {"llm_characters_used": characters_count}},
        upsert=True,
    )


async def ban_user(user_id: int, reason: Optional[str] = None, banned_by: Optional[str] = None) -> bool:
    collection = get_banned_users_collection()
    try:
        banned_user = BannedUser(user_id=user_id, reason=reason, banned_by=banned_by)
        await collection.update_one(
            {"user_id": user_id},
            {"$setOnInsert": banned_user.model_dump(by_alias=True)},
            upsert=True,
        )
        await get_db().users.update_one(
            {"telegram_user_id": user_id},
            {"$set": {"is_banned": True, "updated_at": _utc_now()}},
        )
        return True
    except Exception:
        logger.exception("Failed to ban user %s", user_id)
        return False


async def unban_user(user_id: int) -> bool:
    collection = get_banned_users_collection()
    try:
        result = await collection.delete_one({"user_id": user_id})
        await get_db().users.update_one(
            {"telegram_user_id": user_id},
            {"$set": {"is_banned": False, "updated_at": _utc_now()}},
        )
        return result.deleted_count > 0
    except Exception:
        logger.exception("Failed to unban user %s", user_id)
        return False


async def is_user_banned(user_id: int) -> bool:
    collection = get_banned_users_collection()
    try:
        doc = await collection.find_one({"user_id": user_id}, {"_id": 1})
        return doc is not None
    except Exception:
        logger.exception("Failed to check ban status for user %s", user_id)
        return False


async def get_banned_users() -> list[BannedUser]:
    collection = get_banned_users_collection()
    banned: list[BannedUser] = []
    try:
        async for doc in collection.find({}).sort("banned_at", pymongo.DESCENDING):
            banned.append(BannedUser(**doc))
    except Exception:
        logger.exception("Failed to list banned users.")
    return banned


async def ensure_exchange_user(
    telegram_user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
) -> None:
    database = get_db()
    now = _utc_now()

    await database.users.update_one(
        {"telegram_user_id": telegram_user_id},
        {
            "$set": {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "last_activity_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "telegram_user_id": telegram_user_id,
                "first_seen_at": now,
                "is_banned": False,
                "created_at": now,
            },
        },
        upsert=True,
    )
    await database.bot_users.update_one(
        {"user_id": telegram_user_id},
        {
            "$set": {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "last_seen_at": now,
            },
            "$setOnInsert": {
                "user_id": telegram_user_id,
                "first_seen_at": now,
            },
        },
        upsert=True,
    )


async def delete_exchange_user_data(telegram_user_id: int) -> bool:
    database = get_db()
    users_result = await database.users.delete_one({"telegram_user_id": telegram_user_id})
    bot_users_result = await database.bot_users.delete_one({"user_id": telegram_user_id})
    return users_result.deleted_count > 0 or bot_users_result.deleted_count > 0


async def get_exchange_user(telegram_user_id: int) -> Optional[dict]:
    document = await get_db().users.find_one({"telegram_user_id": telegram_user_id})
    if not document:
        return None
    if "_id" in document:
        document["_id"] = str(document["_id"])
    return document


async def create_material(material: MaterialDB, mirror_legacy: bool = True) -> str:
    database = get_db()
    result = await database.materials.insert_one(material.model_dump())
    material_id = str(result.inserted_id)

    if mirror_legacy:
        legacy_content_type = "text"
        if material.content_type in (MaterialContentType.PHOTO, MaterialContentType.DOCUMENT):
            legacy_content_type = "photo"
        legacy_link = LinkDB(
            user_id=material.user_id,
            username=material.username,
            first_name=material.first_name,
            text=material.text if legacy_content_type == "text" else None,
            telegram_file_id=material.file_id,
            caption=material.text if legacy_content_type == "photo" else None,
            content_type=legacy_content_type,
            file_name=material.file_name,
            mime_type=material.mime_type,
            submitted_at=material.created_at,
        )
        await database.links.insert_one(legacy_link.model_dump(by_alias=True))

    return material_id


async def create_support_message(message: SupportMessageDB) -> str:
    result = await get_db().support_messages.insert_one(message.model_dump())
    return str(result.inserted_id)


async def create_website_submission(submission: WebsiteSubmissionDB) -> str:
    result = await get_website_submissions_collection().insert_one(submission.model_dump())
    return str(result.inserted_id)


async def get_next_order_id() -> str:
    counter = await get_db().counters.find_one_and_update(
        {"_id": "orders"},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"ORD-{counter['value']:05d}"


async def create_order(order: OrderDB) -> str:
    result = await get_db().orders.insert_one(_serialize_order(order))
    return str(result.inserted_id)


async def get_order_by_order_id(order_id: str) -> Optional[dict]:
    document = await get_db().orders.find_one({"order_id": order_id})
    if not document:
        return None
    return _deserialize_order(document)


async def get_order_for_user(order_id: str, user_id: int) -> Optional[dict]:
    document = await get_db().orders.find_one({"order_id": order_id, "user_id": user_id})
    if not document:
        return None
    return _deserialize_order(document)


async def list_orders_for_user(
    user_id: int,
    page: int = 1,
    page_size: int = 10,
    status: Optional[OrderStatus] = None,
) -> tuple[list[dict], int]:
    filters: dict = {"user_id": user_id}
    if status is not None:
        filters["status"] = status.value

    collection = get_db().orders
    total = await collection.count_documents(filters)
    skip = max(page - 1, 0) * page_size
    orders: list[dict] = []
    async for document in collection.find(filters).sort("created_at", pymongo.DESCENDING).skip(skip).limit(page_size):
        orders.append(_deserialize_order(document))
    return orders, total


async def update_order_status_by_order_id(order_id: str, new_status: OrderStatus) -> Optional[dict]:
    now = _utc_now()
    updated_document = await get_db().orders.find_one_and_update(
        {"order_id": order_id},
        {"$set": {"status": new_status.value, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated_document:
        return None
    return _deserialize_order(updated_document)


async def count_orders_for_user(user_id: int) -> int:
    return await get_db().orders.count_documents({"user_id": user_id})


async def count_active_orders_for_user(user_id: int) -> int:
    return await get_db().orders.count_documents(
        {
            "user_id": user_id,
            "status": {"$in": [OrderStatus.NEW.value, OrderStatus.PROCESSING.value, OrderStatus.WAITING_PAYMENT.value]},
        }
    )


async def count_materials_for_user(user_id: int) -> int:
    return await get_db().materials.count_documents({"user_id": user_id})


async def get_all_known_user_ids() -> list[int]:
    database = get_db()
    exchange_ids = await database.users.distinct("telegram_user_id")
    legacy_ids = await database.bot_users.distinct("user_id")
    merged = {int(value) for value in exchange_ids + legacy_ids if value is not None}
    return sorted(merged)


# =============================================================================
# Web User Auth — In-memory storage (temporary, replace with Redis later)
# =============================================================================

_web_users: dict[str, WebUserDB] = {}
_auth_sessions: dict[str, AuthSessionDB] = {}


async def create_web_user(user: WebUserDB) -> WebUserDB:
    _web_users[user.email] = user
    return user


async def get_web_user_by_email(email: str) -> Optional[WebUserDB]:
    return _web_users.get(email.lower())


async def get_web_user_by_id(user_id: str) -> Optional[WebUserDB]:
    for user in _web_users.values():
        if user.id == user_id:
            return user
    return None


async def update_web_user_last_login(user_id: str) -> None:
    now = _utc_now()
    for user in _web_users.values():
        if user.id == user_id:
            user.last_login_at = now
            user.updated_at = now
            return


async def create_auth_session(session: AuthSessionDB) -> AuthSessionDB:
    _auth_sessions[session.session_id] = session
    return session


async def get_auth_session(session_id: str) -> Optional[AuthSessionDB]:
    session = _auth_sessions.get(session_id)
    if session is None:
        return None
    if session.expires_at <= _utc_now():
        _auth_sessions.pop(session_id, None)
        return None
    return session


async def delete_auth_session(session_id: str) -> None:
    _auth_sessions.pop(session_id, None)


async def delete_auth_sessions_for_user(user_id: str) -> None:
    session_ids = [session_id for session_id, session in _auth_sessions.items() if session.user_id == user_id]
    for session_id in session_ids:
        _auth_sessions.pop(session_id, None)


async def set_email_verification_code(user_id: str, code_hash: str, expires_at: datetime) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verification_code_hash = code_hash
            user.email_verification_code_expires_at = expires_at
            user.email_verification_attempts = 0
            user.updated_at = _utc_now()
            return


async def increment_email_verification_attempts(user_id: str) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verification_attempts += 1
            user.updated_at = _utc_now()
            return


async def clear_email_verification_code(user_id: str) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verification_code_hash = None
            user.email_verification_code_expires_at = None
            user.email_verification_attempts = 0
            user.updated_at = _utc_now()
            return


async def mark_web_user_email_verified(user_id: str) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verified = True
            user.email_verification_code_hash = None
            user.email_verification_code_expires_at = None
            user.email_verification_attempts = 0
            user.updated_at = _utc_now()
            return


async def set_password_reset_code(user_id: str, code_hash: str, expires_at: datetime) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.password_reset_code_hash = code_hash
            user.password_reset_code_expires_at = expires_at
            user.password_reset_attempts = 0
            user.updated_at = _utc_now()
            return


async def increment_password_reset_attempts(user_id: str) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.password_reset_attempts += 1
            user.updated_at = _utc_now()
            return


async def clear_password_reset_code(user_id: str) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.password_reset_code_hash = None
            user.password_reset_code_expires_at = None
            user.password_reset_attempts = 0
            user.updated_at = _utc_now()
            return


async def update_web_user_password_hash(user_id: str, password_hash: str) -> None:
    for user in _web_users.values():
        if user.id == user_id:
            user.password_hash = password_hash
            user.updated_at = _utc_now()
            return
