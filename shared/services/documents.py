import asyncio
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from fastapi import UploadFile

from shared import db
from shared.config import settings
from shared.models import MaterialDB
from shared.services.storage import (
    DocumentStorageDeleteError,
    DocumentStorageError,
    DocumentStorageMissingObjectError,
    get_document_storage,
)
from shared.types.enums import ClientDocumentType, DealDocumentType, MaterialContentType

logger = logging.getLogger(__name__)

PROFILE_DOCUMENT_MAX_SIZE_BYTES = 10 * 1024 * 1024
PROFILE_DOCUMENT_DOWNLOAD_TTL_SECONDS = settings.document_storage_presign_ttl_seconds
PROFILE_DOCUMENT_SUPPORTED_FORMATS_LABEL = "PDF, DOC, DOCX, XLS, XLSX, JPG, PNG"
DEAL_DOCUMENT_MAX_SIZE_BYTES = PROFILE_DOCUMENT_MAX_SIZE_BYTES
DEAL_DOCUMENT_DOWNLOAD_TTL_SECONDS = settings.document_storage_presign_ttl_seconds
DEAL_DOCUMENT_SUPPORTED_FORMATS_LABEL = PROFILE_DOCUMENT_SUPPORTED_FORMATS_LABEL

_PROFILE_DOCUMENT_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
_SAFE_FILE_STEM_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class ProfileDocumentValidationError(ValueError):
    """Raised when the uploaded profile document does not satisfy MVP rules."""


class DealDocumentValidationError(ValueError):
    """Raised when the uploaded deal document does not satisfy MVP rules."""


class ProfileDocumentStorageUnavailableError(RuntimeError):
    """Raised when storage is unavailable during upload or cleanup."""


class DealDocumentStorageUnavailableError(RuntimeError):
    """Raised when storage is unavailable during deal-document work."""


class ProfileDocumentPersistenceError(RuntimeError):
    """Raised when the database write fails after storage work."""


class DealDocumentPersistenceError(RuntimeError):
    """Raised when the database write fails after deal-document storage work."""


class ProfileDocumentStoredFileMissingError(RuntimeError):
    """Raised when the database record exists but the stored object does not."""


class DealDocumentStoredFileMissingError(RuntimeError):
    """Raised when the deal document record exists but the stored object does not."""


class ProfileDocumentDownloadUnavailableError(RuntimeError):
    """Raised when the download link cannot be prepared."""


class DealDocumentDownloadUnavailableError(RuntimeError):
    """Raised when the deal document download link cannot be prepared."""


class TelegramDocumentTransferError(RuntimeError):
    """Raised when Telegram source file retrieval fails."""


@dataclass(slots=True)
class PreparedProfileDocumentUpload:
    file_name: str
    mime_type: str
    file_size: int
    s3_key: str
    content: bytes = b""


@dataclass(slots=True)
class PreparedDealDocumentUpload:
    file_name: str
    mime_type: str
    file_size: int
    s3_key: str
    content: bytes = b""


@dataclass(slots=True)
class StoredProfileDocument:
    document: dict
    replaced: bool


@dataclass(slots=True)
class StoredDealDocument:
    document: dict


@dataclass(slots=True)
class DocumentDownloadLink:
    download_url: str
    expires_at: datetime


def _serialize_audit_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc).replace(microsecond=0)
        return normalized.isoformat().replace("+00:00", "Z")
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def audit_document_event(
    *,
    action: str,
    outcome: str,
    scope: str,
    user_id: int | None = None,
    owner_user_id: int | None = None,
    deal_id: str | None = None,
    document_id: str | None = None,
    client_doc_type: ClientDocumentType | str | None = None,
    deal_doc_type: DealDocumentType | str | None = None,
    s3_key: str | None = None,
    file_name: str | None = None,
    reason: str | None = None,
    replaced: bool | None = None,
) -> None:
    payload = {
        "action": action,
        "outcome": outcome,
        "scope": scope,
        "user_id": user_id,
        "owner_user_id": owner_user_id,
        "deal_id": deal_id,
        "document_id": document_id,
        "client_doc_type": client_doc_type,
        "deal_doc_type": deal_doc_type,
        "s3_key": s3_key,
        "file_name": file_name,
        "reason": reason,
        "replaced": replaced,
    }
    serialized_payload = {
        key: _serialize_audit_value(value)
        for key, value in payload.items()
        if value is not None
    }
    log_message = json.dumps(serialized_payload, sort_keys=True, ensure_ascii=True)
    if outcome == "success":
        logger.info("document_audit %s", log_message)
    elif outcome == "denied":
        logger.warning("document_audit %s", log_message)
    else:
        logger.error("document_audit %s", log_message)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_document_name(
    file_name: str | None,
    *,
    validation_error_type: type[ValueError],
    missing_file_name_message: str,
    unsupported_format_message: str,
) -> tuple[str, str]:
    candidate = Path(file_name or "").name.strip()
    if not candidate:
        raise validation_error_type(missing_file_name_message)

    suffix = Path(candidate).suffix.lower()
    if suffix not in _PROFILE_DOCUMENT_MIME_TYPES:
        raise validation_error_type(unsupported_format_message)

    return candidate, suffix


def _normalize_document_identity(value_name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ProfileDocumentValidationError(f"{value_name} is required.")
    return normalized


def _validate_document_metadata(
    *,
    file_name: str | None,
    file_size: int | None = None,
    validation_error_type: type[ValueError],
    missing_file_name_message: str,
    unsupported_format_message: str,
    empty_message: str,
    oversized_message: str,
    max_size_bytes: int,
) -> tuple[str, str]:
    normalized_file_name, suffix = _normalize_document_name(
        file_name,
        validation_error_type=validation_error_type,
        missing_file_name_message=missing_file_name_message,
        unsupported_format_message=unsupported_format_message,
    )
    if file_size is not None:
        if file_size <= 0:
            raise validation_error_type(empty_message)
        if file_size > max_size_bytes:
            raise validation_error_type(oversized_message)
    return normalized_file_name, _PROFILE_DOCUMENT_MIME_TYPES[suffix]


def validate_profile_document_metadata(
    *,
    file_name: str | None,
    file_size: int | None = None,
) -> tuple[str, str]:
    return _validate_document_metadata(
        file_name=file_name,
        file_size=file_size,
        validation_error_type=ProfileDocumentValidationError,
        missing_file_name_message="Profile document file name is required.",
        unsupported_format_message="Unsupported profile document format.",
        empty_message="Profile documents cannot be empty.",
        oversized_message="Profile documents must be 10 MB or smaller.",
        max_size_bytes=PROFILE_DOCUMENT_MAX_SIZE_BYTES,
    )


def validate_deal_document_metadata(
    *,
    file_name: str | None,
    file_size: int | None = None,
) -> tuple[str, str]:
    return _validate_document_metadata(
        file_name=file_name,
        file_size=file_size,
        validation_error_type=DealDocumentValidationError,
        missing_file_name_message="Deal document file name is required.",
        unsupported_format_message="Unsupported deal document format.",
        empty_message="Deal documents cannot be empty.",
        oversized_message="Deal documents must be 10 MB or smaller.",
        max_size_bytes=DEAL_DOCUMENT_MAX_SIZE_BYTES,
    )


def build_profile_document_s3_key(
    *,
    user_id: int,
    client_doc_type: ClientDocumentType,
    file_name: str,
    uploaded_at: datetime,
) -> str:
    safe_stem = _SAFE_FILE_STEM_RE.sub("-", Path(file_name).stem).strip("-._") or "document"
    suffix = Path(file_name).suffix.lower()
    object_token = secrets.token_hex(8)
    timestamp = uploaded_at.strftime("%Y%m%dT%H%M%SZ")
    return f"documents/users/{user_id}/{client_doc_type.value}/{timestamp}-{object_token}-{safe_stem}{suffix}"


def build_deal_document_s3_key(
    *,
    deal_id: str,
    deal_doc_type: DealDocumentType,
    file_name: str,
    uploaded_at: datetime,
) -> str:
    safe_stem = _SAFE_FILE_STEM_RE.sub("-", Path(file_name).stem).strip("-._") or "document"
    suffix = Path(file_name).suffix.lower()
    object_token = secrets.token_hex(8)
    timestamp = uploaded_at.strftime("%Y%m%dT%H%M%SZ")
    normalized_deal_id = _normalize_document_identity("deal_id", deal_id)
    return f"documents/deals/{normalized_deal_id}/{deal_doc_type.value}/{timestamp}-{object_token}-{safe_stem}{suffix}"


def prepare_profile_document_content(
    *,
    user_id: int,
    client_doc_type: ClientDocumentType,
    file_name: str | None,
    content: bytes,
) -> PreparedProfileDocumentUpload:
    normalized_file_name, mime_type = validate_profile_document_metadata(
        file_name=file_name,
        file_size=len(content),
    )

    uploaded_at = _utc_now()
    return PreparedProfileDocumentUpload(
        file_name=normalized_file_name,
        mime_type=mime_type,
        file_size=len(content),
        s3_key=build_profile_document_s3_key(
            user_id=user_id,
            client_doc_type=client_doc_type,
            file_name=normalized_file_name,
            uploaded_at=uploaded_at,
        ),
        content=content,
    )


def prepare_deal_document_content(
    *,
    deal_id: str,
    deal_doc_type: DealDocumentType,
    file_name: str | None,
    content: bytes,
) -> PreparedDealDocumentUpload:
    normalized_file_name, mime_type = validate_deal_document_metadata(
        file_name=file_name,
        file_size=len(content),
    )

    uploaded_at = _utc_now()
    return PreparedDealDocumentUpload(
        file_name=normalized_file_name,
        mime_type=mime_type,
        file_size=len(content),
        s3_key=build_deal_document_s3_key(
            deal_id=deal_id,
            deal_doc_type=deal_doc_type,
            file_name=normalized_file_name,
            uploaded_at=uploaded_at,
        ),
        content=content,
    )


async def _read_upload_bytes(
    upload: UploadFile,
    *,
    max_size_bytes: int,
    validation_error_type: type[ValueError],
    oversized_message: str,
    empty_message: str,
) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    try:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_size_bytes:
                raise validation_error_type(oversized_message)
            chunks.append(chunk)
    finally:
        await upload.close()

    if total_size <= 0:
        raise validation_error_type(empty_message)
    return b"".join(chunks)


async def prepare_profile_document_upload(
    *,
    user_id: int,
    client_doc_type: ClientDocumentType,
    upload: UploadFile,
) -> PreparedProfileDocumentUpload:
    try:
        content = await _read_upload_bytes(
            upload,
            max_size_bytes=PROFILE_DOCUMENT_MAX_SIZE_BYTES,
            validation_error_type=ProfileDocumentValidationError,
            oversized_message="Profile documents must be 10 MB or smaller.",
            empty_message="Profile documents cannot be empty.",
        )
        return prepare_profile_document_content(
            user_id=user_id,
            client_doc_type=client_doc_type,
            file_name=upload.filename,
            content=content,
        )
    except Exception:
        if not upload.file.closed:
            await upload.close()
        raise


async def prepare_deal_document_upload(
    *,
    deal_id: str,
    deal_doc_type: DealDocumentType,
    upload: UploadFile,
) -> PreparedDealDocumentUpload:
    try:
        content = await _read_upload_bytes(
            upload,
            max_size_bytes=DEAL_DOCUMENT_MAX_SIZE_BYTES,
            validation_error_type=DealDocumentValidationError,
            oversized_message="Deal documents must be 10 MB or smaller.",
            empty_message="Deal documents cannot be empty.",
        )
        return prepare_deal_document_content(
            deal_id=deal_id,
            deal_doc_type=deal_doc_type,
            file_name=upload.filename,
            content=content,
        )
    except Exception:
        if not upload.file.closed:
            await upload.close()
        raise


async def store_prepared_profile_document(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    client_doc_type: ClientDocumentType,
    prepared_upload: PreparedProfileDocumentUpload,
    telegram_file_id: str | None = None,
) -> StoredProfileDocument:
    storage = get_document_storage()
    existing_document = await db.get_profile_document_by_type(user_id, client_doc_type.value)
    audit_action = "replace" if existing_document is not None else "upload"

    try:
        await storage.upload_bytes(
            object_key=prepared_upload.s3_key,
            payload=prepared_upload.content,
            content_type=prepared_upload.mime_type,
        )
    except DocumentStorageError as exc:
        logger.exception(
            "Profile document storage upload failed. user_id=%s client_doc_type=%s s3_key=%s",
            user_id,
            client_doc_type.value,
            prepared_upload.s3_key,
        )
        audit_document_event(
            action=audit_action,
            outcome="failure",
            scope="profile",
            user_id=user_id,
            client_doc_type=client_doc_type,
            s3_key=prepared_upload.s3_key,
            file_name=prepared_upload.file_name,
            replaced=existing_document is not None,
            reason="storage_upload_failed",
        )
        raise ProfileDocumentStorageUnavailableError("Profile document storage is temporarily unavailable.") from exc

    try:
        saved_document = await db.create_or_replace_client_document(
            MaterialDB(
                user_id=user_id,
                username=username,
                first_name=first_name,
                content_type=MaterialContentType.CLIENT_DOC,
                client_doc_type=client_doc_type,
                telegram_file_id=telegram_file_id,
                file_name=prepared_upload.file_name,
                mime_type=prepared_upload.mime_type,
                file_size=prepared_upload.file_size,
                s3_key=prepared_upload.s3_key,
            )
        )
    except Exception as exc:
        logger.exception(
            "Profile document persistence failed after storage upload. user_id=%s client_doc_type=%s s3_key=%s",
            user_id,
            client_doc_type.value,
            prepared_upload.s3_key,
        )
        try:
            await storage.delete_object(object_key=prepared_upload.s3_key, missing_ok=True)
        except DocumentStorageDeleteError:
            logger.exception(
                "Profile document rollback delete failed. user_id=%s client_doc_type=%s s3_key=%s",
                user_id,
                client_doc_type.value,
                prepared_upload.s3_key,
            )
        audit_document_event(
            action=audit_action,
            outcome="failure",
            scope="profile",
            user_id=user_id,
            client_doc_type=client_doc_type,
            s3_key=prepared_upload.s3_key,
            file_name=prepared_upload.file_name,
            replaced=existing_document is not None,
            reason="persistence_failed",
        )
        raise ProfileDocumentPersistenceError("Profile document could not be saved.") from exc

    replaced = existing_document is not None
    previous_s3_key = existing_document.get("s3_key") if existing_document else None
    if previous_s3_key and previous_s3_key != prepared_upload.s3_key:
        try:
            await storage.delete_object(object_key=previous_s3_key, missing_ok=True)
        except DocumentStorageDeleteError:
            logger.exception(
                "Profile document replacement cleanup failed. user_id=%s old_s3_key=%s new_s3_key=%s",
                user_id,
                previous_s3_key,
                prepared_upload.s3_key,
            )

    audit_document_event(
        action=audit_action,
        outcome="success",
        scope="profile",
        user_id=user_id,
        document_id=saved_document["id"],
        client_doc_type=client_doc_type,
        s3_key=prepared_upload.s3_key,
        file_name=prepared_upload.file_name,
        replaced=replaced,
    )
    return StoredProfileDocument(document=saved_document, replaced=replaced)


async def store_prepared_deal_document(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    deal_id: str,
    deal_doc_type: DealDocumentType,
    prepared_upload: PreparedDealDocumentUpload,
    telegram_file_id: str | None = None,
) -> StoredDealDocument:
    storage = get_document_storage()

    try:
        await storage.upload_bytes(
            object_key=prepared_upload.s3_key,
            payload=prepared_upload.content,
            content_type=prepared_upload.mime_type,
        )
    except DocumentStorageError as exc:
        logger.exception(
            "Deal document storage upload failed. deal_id=%s user_id=%s deal_doc_type=%s s3_key=%s",
            deal_id,
            user_id,
            deal_doc_type.value,
            prepared_upload.s3_key,
        )
        audit_document_event(
            action="deal_link",
            outcome="failure",
            scope="deal",
            user_id=user_id,
            deal_id=deal_id,
            deal_doc_type=deal_doc_type,
            s3_key=prepared_upload.s3_key,
            file_name=prepared_upload.file_name,
            reason="storage_upload_failed",
        )
        raise DealDocumentStorageUnavailableError("Deal document storage is temporarily unavailable.") from exc

    try:
        saved_document = await db.create_deal_document(
            MaterialDB(
                user_id=user_id,
                username=username,
                first_name=first_name,
                content_type=MaterialContentType.DEAL_DOC,
                deal_doc_type=deal_doc_type,
                deal_id=deal_id,
                telegram_file_id=telegram_file_id,
                file_name=prepared_upload.file_name,
                mime_type=prepared_upload.mime_type,
                file_size=prepared_upload.file_size,
                s3_key=prepared_upload.s3_key,
            )
        )
    except Exception as exc:
        logger.exception(
            "Deal document persistence failed after storage upload. deal_id=%s user_id=%s deal_doc_type=%s s3_key=%s",
            deal_id,
            user_id,
            deal_doc_type.value,
            prepared_upload.s3_key,
        )
        try:
            await storage.delete_object(object_key=prepared_upload.s3_key, missing_ok=True)
        except DocumentStorageDeleteError:
            logger.exception(
                "Deal document rollback delete failed. deal_id=%s user_id=%s s3_key=%s",
                deal_id,
                user_id,
                prepared_upload.s3_key,
            )
        audit_document_event(
            action="deal_link",
            outcome="failure",
            scope="deal",
            user_id=user_id,
            deal_id=deal_id,
            deal_doc_type=deal_doc_type,
            s3_key=prepared_upload.s3_key,
            file_name=prepared_upload.file_name,
            reason="persistence_failed",
        )
        raise DealDocumentPersistenceError("Deal document could not be saved.") from exc

    audit_document_event(
        action="deal_link",
        outcome="success",
        scope="deal",
        user_id=user_id,
        deal_id=deal_id,
        document_id=saved_document["id"],
        deal_doc_type=deal_doc_type,
        s3_key=prepared_upload.s3_key,
        file_name=prepared_upload.file_name,
    )
    return StoredDealDocument(document=saved_document)


async def store_profile_document_upload(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    client_doc_type: ClientDocumentType,
    upload: UploadFile,
) -> StoredProfileDocument:
    prepared_upload = await prepare_profile_document_upload(
        user_id=user_id,
        client_doc_type=client_doc_type,
        upload=upload,
    )
    return await store_prepared_profile_document(
        user_id=user_id,
        username=username,
        first_name=first_name,
        client_doc_type=client_doc_type,
        prepared_upload=prepared_upload,
    )


async def store_deal_document_upload(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    deal_id: str,
    deal_doc_type: DealDocumentType,
    upload: UploadFile,
) -> StoredDealDocument:
    prepared_upload = await prepare_deal_document_upload(
        deal_id=deal_id,
        deal_doc_type=deal_doc_type,
        upload=upload,
    )
    return await store_prepared_deal_document(
        user_id=user_id,
        username=username,
        first_name=first_name,
        deal_id=deal_id,
        deal_doc_type=deal_doc_type,
        prepared_upload=prepared_upload,
    )


def _download_telegram_file_content_sync(*, telegram_file_id: str) -> bytes:
    token = settings.telegram_bot_token.strip()
    if not token:
        raise TelegramDocumentTransferError("Telegram bot token is not configured.")

    encoded_query = urlencode({"file_id": telegram_file_id})
    get_file_url = f"https://api.telegram.org/bot{token}/getFile?{encoded_query}"
    with urlopen(get_file_url, timeout=settings.document_storage_timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    file_path = payload.get("result", {}).get("file_path")
    if not payload.get("ok") or not file_path:
        raise TelegramDocumentTransferError("Telegram source file could not be resolved.")

    download_url = f"https://api.telegram.org/file/bot{token}/{quote(file_path, safe='/')}"
    with urlopen(download_url, timeout=settings.document_storage_timeout_seconds) as response:
        return response.read()


async def download_telegram_file_content(*, telegram_file_id: str) -> bytes:
    normalized_file_id = _normalize_document_identity("telegram_file_id", telegram_file_id)
    try:
        return await asyncio.to_thread(
            _download_telegram_file_content_sync,
            telegram_file_id=normalized_file_id,
        )
    except TelegramDocumentTransferError:
        raise
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        logger.exception("Telegram file download failed. telegram_file_id=%s", normalized_file_id)
        raise TelegramDocumentTransferError("Telegram source file could not be downloaded.") from exc


async def transfer_profile_document_from_telegram(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    client_doc_type: ClientDocumentType,
    telegram_file_id: str,
    file_name: str | None,
) -> StoredProfileDocument:
    file_bytes = await download_telegram_file_content(telegram_file_id=telegram_file_id)
    prepared_upload = prepare_profile_document_content(
        user_id=user_id,
        client_doc_type=client_doc_type,
        file_name=file_name,
        content=file_bytes,
    )
    return await store_prepared_profile_document(
        user_id=user_id,
        username=username,
        first_name=first_name,
        client_doc_type=client_doc_type,
        prepared_upload=prepared_upload,
        telegram_file_id=telegram_file_id,
    )


def build_profile_document_download_link(*, s3_key: str) -> DocumentDownloadLink:
    try:
        presigned = get_document_storage().build_presigned_download_url(
            object_key=s3_key,
            expires_in_seconds=PROFILE_DOCUMENT_DOWNLOAD_TTL_SECONDS,
        )
    except DocumentStorageError as exc:
        raise ProfileDocumentDownloadUnavailableError("Profile document download is temporarily unavailable.") from exc

    return DocumentDownloadLink(
        download_url=presigned.url,
        expires_at=presigned.expires_at,
    )


def build_deal_document_download_link(*, s3_key: str) -> DocumentDownloadLink:
    try:
        presigned = get_document_storage().build_presigned_download_url(
            object_key=s3_key,
            expires_in_seconds=DEAL_DOCUMENT_DOWNLOAD_TTL_SECONDS,
        )
    except DocumentStorageError as exc:
        raise DealDocumentDownloadUnavailableError("Deal document download is temporarily unavailable.") from exc

    return DocumentDownloadLink(
        download_url=presigned.url,
        expires_at=presigned.expires_at,
    )


async def issue_profile_document_download_link(*, s3_key: str) -> DocumentDownloadLink:
    storage = get_document_storage()
    try:
        await storage.ensure_object_exists(object_key=s3_key)
    except DocumentStorageMissingObjectError as exc:
        logger.error("Stored profile document object is missing. s3_key=%s", s3_key)
        audit_document_event(
            action="download",
            outcome="failure",
            scope="profile",
            s3_key=s3_key,
            reason="stored_object_missing",
        )
        raise ProfileDocumentStoredFileMissingError("Stored profile document file is missing.") from exc
    except DocumentStorageError as exc:
        logger.exception("Profile document storage lookup failed before download. s3_key=%s", s3_key)
        audit_document_event(
            action="download",
            outcome="failure",
            scope="profile",
            s3_key=s3_key,
            reason="storage_lookup_failed",
        )
        raise ProfileDocumentDownloadUnavailableError("Profile document download is temporarily unavailable.") from exc

    return build_profile_document_download_link(s3_key=s3_key)


async def issue_deal_document_download_link(*, s3_key: str) -> DocumentDownloadLink:
    storage = get_document_storage()
    try:
        await storage.ensure_object_exists(object_key=s3_key)
    except DocumentStorageMissingObjectError as exc:
        logger.error("Stored deal document object is missing. s3_key=%s", s3_key)
        audit_document_event(
            action="download",
            outcome="failure",
            scope="deal",
            s3_key=s3_key,
            reason="stored_object_missing",
        )
        raise DealDocumentStoredFileMissingError("Stored deal document file is missing.") from exc
    except DocumentStorageError as exc:
        logger.exception("Deal document storage lookup failed before download. s3_key=%s", s3_key)
        audit_document_event(
            action="download",
            outcome="failure",
            scope="deal",
            s3_key=s3_key,
            reason="storage_lookup_failed",
        )
        raise DealDocumentDownloadUnavailableError("Deal document download is temporarily unavailable.") from exc

    return build_deal_document_download_link(s3_key=s3_key)


async def delete_stored_profile_document(*, s3_key: str) -> None:
    try:
        await get_document_storage().delete_object(object_key=s3_key, missing_ok=True)
    except DocumentStorageDeleteError as exc:
        raise ProfileDocumentStorageUnavailableError("Profile document storage is temporarily unavailable.") from exc
