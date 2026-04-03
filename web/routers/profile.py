import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from shared import db
from shared.models import LimitQuotaDB, NotificationPreferences, WebUserDB
from shared.services import documents as document_service
from shared.security_settings import calculate_remaining_quota
from shared.services.security_settings import create_pending_whitelist_entry
from shared.types.enums import ClientDocumentType
from web.auth import get_current_user
from web.models import (
    CreateWhitelistAddressRequest,
    ProfileDocumentDownloadResponse,
    ProfileDocumentResponse,
    ProfileLimitsResponse,
    SimpleSuccessResponse,
    UpdateWhitelistAddressLabelRequest,
    WhitelistAddressResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["Profile"])

UNLINKED_EXCHANGE_USER_MESSAGE = "Current web account is not linked to an exchange user."
MISSING_EXCHANGE_USER_MESSAGE = "Current web account is linked to a missing exchange user."
MISSING_LIMIT_QUOTA_MESSAGE = "Limit quota is not configured for current exchange user."
MISSING_NOTIFICATION_PREFERENCES_MESSAGE = "Notification preferences are not configured for current exchange user."
PROFILE_DOCUMENT_NOT_FOUND_MESSAGE = "Profile document not found."
PROFILE_DOCUMENT_FORBIDDEN_MESSAGE = "You do not have access to this profile document."
WHITELIST_ENTRY_NOT_FOUND_MESSAGE = "Whitelist entry not found."
WHITELIST_ENTRY_IN_USE_MESSAGE = "Whitelist entry is used by an active order and cannot be deleted."
WHITELIST_REJECTED_DELETE_MESSAGE = "Rejected whitelist entries cannot be deleted."


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _require_linked_exchange_user_id(current_user: WebUserDB) -> int:
    if current_user.linked_exchange_user_id is None:
        logger.error("Profile API rejected because web user is not linked. user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=UNLINKED_EXCHANGE_USER_MESSAGE,
        )
    return current_user.linked_exchange_user_id


async def _require_exchange_user(current_user: WebUserDB) -> tuple[int, dict]:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    exchange_user = await db.get_exchange_user(exchange_user_id)
    if exchange_user is None:
        logger.error(
            "Profile API rejected because linked exchange user is missing. web_user_id=%s exchange_user_id=%s",
            current_user.id,
            exchange_user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MISSING_EXCHANGE_USER_MESSAGE,
        )
    return exchange_user_id, exchange_user


def _serialize_whitelist_entry(entry: dict) -> WhitelistAddressResponse:
    return WhitelistAddressResponse(
        id=entry["id"],
        network=entry["network"],
        address=entry["address"],
        label=entry["label"],
        status=entry["status"],
        rejection_reason=entry.get("rejection_reason"),
        verified_by=entry.get("verified_by"),
        verified_at=entry.get("verified_at"),
        created_at=entry["created_at"],
        updated_at=entry["updated_at"],
    )


def _serialize_profile_document(entry: dict) -> ProfileDocumentResponse:
    return ProfileDocumentResponse(
        id=entry["id"],
        type=entry["client_doc_type"],
        file_name=entry["file_name"],
        file_size=entry["file_size"],
        created_at=entry["created_at"],
    )


async def _require_owned_profile_document(user_id: int, document_id: str, *, action: str) -> dict:
    document = await db.get_profile_document(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PROFILE_DOCUMENT_NOT_FOUND_MESSAGE)
    if document["user_id"] != user_id:
        logger.warning(
            "Profile document access denied. user_id=%s document_id=%s owner_user_id=%s",
            user_id,
            document_id,
            document["user_id"],
        )
        document_service.audit_document_event(
            action=action,
            outcome="denied",
            scope="profile",
            user_id=user_id,
            owner_user_id=document["user_id"],
            document_id=document_id,
            client_doc_type=document.get("client_doc_type"),
            s3_key=document.get("s3_key"),
            reason="owner_mismatch",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PROFILE_DOCUMENT_FORBIDDEN_MESSAGE)
    return document


@router.get("/limits", response_model=ProfileLimitsResponse)
async def get_profile_limits(current_user: WebUserDB = Depends(get_current_user)) -> ProfileLimitsResponse:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    quota_payload = await db.get_limit_quota(exchange_user_id)
    if quota_payload is None:
        logger.error("Profile limits requested without configured quota. exchange_user_id=%s", exchange_user_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MISSING_LIMIT_QUOTA_MESSAGE,
        )

    try:
        quota = LimitQuotaDB(**quota_payload)
    except ValidationError as exc:
        logger.exception("Stored limit quota is invalid. exchange_user_id=%s", exchange_user_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MISSING_LIMIT_QUOTA_MESSAGE,
        ) from exc

    return ProfileLimitsResponse(
        verification_level=quota.verification_level,
        daily_limit=_format_decimal(quota.daily_limit),
        daily_used=_format_decimal(quota.daily_used),
        daily_remaining=_format_decimal(calculate_remaining_quota(quota.daily_limit, quota.daily_used)),
        daily_reset_at=quota.daily_reset_at,
        monthly_limit=_format_decimal(quota.monthly_limit),
        monthly_used=_format_decimal(quota.monthly_used),
        monthly_remaining=_format_decimal(calculate_remaining_quota(quota.monthly_limit, quota.monthly_used)),
        monthly_reset_at=quota.monthly_reset_at,
        updated_at=quota.updated_at,
    )


@router.get("/notifications", response_model=NotificationPreferences)
async def get_profile_notifications(current_user: WebUserDB = Depends(get_current_user)) -> NotificationPreferences:
    exchange_user_id, exchange_user = await _require_exchange_user(current_user)
    try:
        return NotificationPreferences(**exchange_user["notification_preferences"])
    except KeyError as exc:
        logger.error("Notification preferences are missing in exchange user profile. exchange_user_id=%s", exchange_user_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MISSING_NOTIFICATION_PREFERENCES_MESSAGE,
        ) from exc
    except ValidationError as exc:
        logger.exception("Stored notification preferences are invalid. exchange_user_id=%s", exchange_user_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MISSING_NOTIFICATION_PREFERENCES_MESSAGE,
        ) from exc


@router.put("/notifications", response_model=NotificationPreferences)
async def update_profile_notifications(
    payload: NotificationPreferences,
    current_user: WebUserDB = Depends(get_current_user),
) -> NotificationPreferences:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    updated = await db.update_exchange_user_notification_preferences(exchange_user_id, payload)
    if not updated:
        logger.error("Notification preferences update failed because exchange user disappeared. exchange_user_id=%s", exchange_user_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MISSING_EXCHANGE_USER_MESSAGE,
        )
    return payload


@router.get("/documents", response_model=list[ProfileDocumentResponse])
async def list_profile_documents(current_user: WebUserDB = Depends(get_current_user)) -> list[ProfileDocumentResponse]:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    documents = await db.list_profile_documents(exchange_user_id)
    return [_serialize_profile_document(document) for document in documents]


@router.post("/documents", response_model=ProfileDocumentResponse)
async def upload_profile_document(
    response: Response,
    document_type: ClientDocumentType = Form(..., alias="type"),
    file: UploadFile = File(...),
    current_user: WebUserDB = Depends(get_current_user),
) -> ProfileDocumentResponse:
    exchange_user_id, exchange_user = await _require_exchange_user(current_user)
    try:
        stored_document = await document_service.store_profile_document_upload(
            user_id=exchange_user_id,
            username=exchange_user.get("username"),
            first_name=exchange_user.get("first_name"),
            client_doc_type=document_type,
            upload=file,
        )
    except document_service.ProfileDocumentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (
        document_service.ProfileDocumentStorageUnavailableError,
        document_service.ProfileDocumentPersistenceError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    response.status_code = status.HTTP_200_OK if stored_document.replaced else status.HTTP_201_CREATED
    logger.info(
        "Profile document saved. user_id=%s document_id=%s client_doc_type=%s replaced=%s",
        exchange_user_id,
        stored_document.document["id"],
        document_type.value,
        stored_document.replaced,
    )
    return _serialize_profile_document(stored_document.document)


@router.delete("/documents/{document_id}", response_model=SimpleSuccessResponse)
async def delete_profile_document(
    document_id: str,
    current_user: WebUserDB = Depends(get_current_user),
) -> SimpleSuccessResponse:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    document = await _require_owned_profile_document(exchange_user_id, document_id, action="delete")
    deleted = await db.delete_profile_document(exchange_user_id, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PROFILE_DOCUMENT_NOT_FOUND_MESSAGE)
    try:
        await document_service.delete_stored_profile_document(s3_key=document["s3_key"])
    except document_service.ProfileDocumentStorageUnavailableError:
        logger.exception(
            "Profile document storage cleanup failed after delete. user_id=%s document_id=%s s3_key=%s",
            exchange_user_id,
            document_id,
            document["s3_key"],
        )
    logger.info("Profile document deleted. user_id=%s document_id=%s s3_key=%s", exchange_user_id, document_id, document["s3_key"])
    document_service.audit_document_event(
        action="delete",
        outcome="success",
        scope="profile",
        user_id=exchange_user_id,
        document_id=document_id,
        client_doc_type=document.get("client_doc_type"),
        s3_key=document.get("s3_key"),
        file_name=document.get("file_name"),
    )
    return SimpleSuccessResponse(message="Profile document deleted successfully.")


@router.get("/documents/{document_id}/download", response_model=ProfileDocumentDownloadResponse)
async def get_profile_document_download_link(
    document_id: str,
    current_user: WebUserDB = Depends(get_current_user),
) -> ProfileDocumentDownloadResponse:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    document = await _require_owned_profile_document(exchange_user_id, document_id, action="download")
    try:
        download_link = await document_service.issue_profile_document_download_link(s3_key=document["s3_key"])
    except document_service.ProfileDocumentStoredFileMissingError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except document_service.ProfileDocumentDownloadUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    logger.info("Profile document download issued. user_id=%s document_id=%s", exchange_user_id, document_id)
    document_service.audit_document_event(
        action="download",
        outcome="success",
        scope="profile",
        user_id=exchange_user_id,
        document_id=document_id,
        client_doc_type=document.get("client_doc_type"),
        s3_key=document.get("s3_key"),
        file_name=document.get("file_name"),
    )
    return ProfileDocumentDownloadResponse(
        download_url=download_link.download_url,
        expires_at=download_link.expires_at,
    )


@router.get("/whitelist", response_model=list[WhitelistAddressResponse])
async def list_profile_whitelist(current_user: WebUserDB = Depends(get_current_user)) -> list[WhitelistAddressResponse]:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    entries = await db.list_whitelist_addresses_for_user(exchange_user_id)
    return [_serialize_whitelist_entry(entry) for entry in entries]


@router.post("/whitelist", response_model=WhitelistAddressResponse, status_code=status.HTTP_201_CREATED)
async def create_profile_whitelist_entry(
    payload: CreateWhitelistAddressRequest,
    current_user: WebUserDB = Depends(get_current_user),
) -> WhitelistAddressResponse:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    try:
        saved_entry = await create_pending_whitelist_entry(
            user_id=exchange_user_id,
            network=payload.network,
            address=payload.address,
            label=payload.label,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _serialize_whitelist_entry(saved_entry.model_dump())


@router.put("/whitelist/{whitelist_id}", response_model=WhitelistAddressResponse)
async def update_profile_whitelist_entry(
    whitelist_id: str,
    payload: UpdateWhitelistAddressLabelRequest,
    current_user: WebUserDB = Depends(get_current_user),
) -> WhitelistAddressResponse:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    try:
        updated_entry = await db.update_whitelist_address_label(exchange_user_id, whitelist_id, payload.label)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if updated_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WHITELIST_ENTRY_NOT_FOUND_MESSAGE)
    return _serialize_whitelist_entry(updated_entry)


@router.delete("/whitelist/{whitelist_id}", response_model=SimpleSuccessResponse)
async def delete_profile_whitelist_entry(
    whitelist_id: str,
    current_user: WebUserDB = Depends(get_current_user),
) -> SimpleSuccessResponse:
    exchange_user_id, _ = await _require_exchange_user(current_user)
    entry = await db.get_whitelist_address_for_user(exchange_user_id, whitelist_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WHITELIST_ENTRY_NOT_FOUND_MESSAGE)
    if entry["status"] == "rejected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=WHITELIST_REJECTED_DELETE_MESSAGE)

    active_order_count = await db.count_active_orders_for_whitelist_address(
        user_id=exchange_user_id,
        whitelist_address_id=entry["id"],
        wallet_address=entry["address"],
        wallet_network=entry["network"],
    )
    if active_order_count > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=WHITELIST_ENTRY_IN_USE_MESSAGE)

    deleted = await db.delete_whitelist_address(exchange_user_id, whitelist_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=WHITELIST_ENTRY_NOT_FOUND_MESSAGE)
    return SimpleSuccessResponse(message="Whitelist entry deleted successfully.")
