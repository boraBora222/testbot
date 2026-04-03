import asyncio
import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from shared.config import settings

logger = logging.getLogger(__name__)

_AWS_ALGORITHM = "AWS4-HMAC-SHA256"
_SERVICE_NAME = "s3"
_EMPTY_PAYLOAD_SHA256 = hashlib.sha256(b"").hexdigest()


class DocumentStorageError(RuntimeError):
    """Base error for document storage operations."""


class DocumentStorageConfigurationError(DocumentStorageError):
    """Raised when document storage settings are incomplete."""


class DocumentStorageUploadError(DocumentStorageError):
    """Raised when an object upload fails."""


class DocumentStorageDeleteError(DocumentStorageError):
    """Raised when an object deletion fails."""


class DocumentStorageMissingObjectError(DocumentStorageError):
    """Raised when the stored object cannot be found."""


class DocumentStorageDownloadLinkError(DocumentStorageError):
    """Raised when a presigned URL cannot be generated."""


@dataclass(slots=True)
class PresignedObjectUrl:
    url: str
    expires_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_required_setting(field_name: str, value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise DocumentStorageConfigurationError(f"{field_name} is not configured.")
    return normalized


def _hash_payload(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _derive_signing_key(secret_key: str, datestamp: str, region: str) -> bytes:
    key_date = hmac.new(f"AWS4{secret_key}".encode("utf-8"), datestamp.encode("utf-8"), hashlib.sha256).digest()
    key_region = hmac.new(key_date, region.encode("utf-8"), hashlib.sha256).digest()
    key_service = hmac.new(key_region, _SERVICE_NAME.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()


def _canonicalize_query(parameters: list[tuple[str, str]]) -> str:
    encoded_pairs: list[str] = []
    for key, value in sorted(parameters):
        encoded_pairs.append(
            f"{quote(str(key), safe='-_.~')}={quote(str(value), safe='-_.~')}"
        )
    return "&".join(encoded_pairs)


def _canonicalize_headers(headers: dict[str, str]) -> tuple[str, str]:
    normalized_headers = {
        key.lower(): " ".join(value.strip().split())
        for key, value in headers.items()
        if value is not None
    }
    sorted_keys = sorted(normalized_headers)
    canonical_headers = "".join(f"{key}:{normalized_headers[key]}\n" for key in sorted_keys)
    signed_headers = ";".join(sorted_keys)
    return canonical_headers, signed_headers


class S3CompatibleDocumentStorage:
    """Minimal S3-compatible client for document uploads and presigned downloads."""

    def __init__(
        self,
        *,
        endpoint: str,
        public_endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        timeout_seconds: int,
    ) -> None:
        self.endpoint = _normalize_required_setting("document_storage_endpoint", endpoint).rstrip("/")
        self.public_endpoint = _normalize_required_setting(
            "document_storage_public_endpoint",
            public_endpoint,
        ).rstrip("/")
        self.bucket = _normalize_required_setting("document_storage_bucket", bucket)
        self.access_key = _normalize_required_setting("document_storage_access_key", access_key)
        self.secret_key = _normalize_required_setting("document_storage_secret_key", secret_key)
        self.region = _normalize_required_setting("document_storage_region", region)
        self.timeout_seconds = timeout_seconds

    def _build_object_uri(self, *, endpoint: str, object_key: str) -> tuple[str, str]:
        normalized_key = object_key.lstrip("/")
        if not normalized_key:
            raise DocumentStorageConfigurationError("document object key cannot be empty.")

        parsed = urlsplit(endpoint)
        base_path = parsed.path.rstrip("/")
        bucket_path = quote(self.bucket.strip("/"), safe="-_.~")
        object_path = quote(normalized_key, safe="/-_.~")
        uri = f"{base_path}/{bucket_path}/{object_path}" if base_path else f"/{bucket_path}/{object_path}"
        host = parsed.netloc
        if not host:
            raise DocumentStorageConfigurationError("document storage endpoint host is invalid.")
        return uri, host

    def _build_request_url(
        self,
        *,
        endpoint: str,
        object_key: str,
        query_parameters: list[tuple[str, str]] | None = None,
    ) -> tuple[str, str, str]:
        parsed = urlsplit(endpoint)
        uri, host = self._build_object_uri(endpoint=endpoint, object_key=object_key)
        query = _canonicalize_query(query_parameters or [])
        return urlunsplit((parsed.scheme, parsed.netloc, uri, query, "")), uri, host

    def _build_authorization_headers(
        self,
        *,
        method: str,
        uri: str,
        host: str,
        payload_hash: str,
        extra_headers: dict[str, str] | None = None,
        query_parameters: list[tuple[str, str]] | None = None,
        requested_at: datetime | None = None,
    ) -> dict[str, str]:
        now = requested_at or _utc_now()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if extra_headers:
            headers.update(extra_headers)

        canonical_headers, signed_headers = _canonicalize_headers(headers)
        canonical_request = "\n".join(
            [
                method,
                uri,
                _canonicalize_query(query_parameters or []),
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{datestamp}/{self.region}/{_SERVICE_NAME}/aws4_request"
        string_to_sign = "\n".join(
            [
                _AWS_ALGORITHM,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            _derive_signing_key(self.secret_key, datestamp, self.region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["Authorization"] = (
            f"{_AWS_ALGORITHM} "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        return headers

    async def _perform_request(
        self,
        *,
        method: str,
        object_key: str,
        payload: bytes = b"",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        request_url, uri, host = self._build_request_url(endpoint=self.endpoint, object_key=object_key)
        payload_hash = _hash_payload(payload)
        headers = self._build_authorization_headers(
            method=method,
            uri=uri,
            host=host,
            payload_hash=payload_hash,
            extra_headers=extra_headers,
        )

        def _send() -> None:
            request = Request(
                url=request_url,
                data=payload if method in {"PUT", "POST"} else None,
                method=method,
                headers=headers,
            )
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()

        await asyncio.to_thread(_send)

    async def upload_bytes(self, *, object_key: str, payload: bytes, content_type: str) -> None:
        if not payload:
            raise DocumentStorageUploadError("Cannot upload an empty document payload.")
        try:
            await self._perform_request(
                method="PUT",
                object_key=object_key,
                payload=payload,
                extra_headers={
                    "content-length": str(len(payload)),
                    "content-type": content_type,
                },
            )
        except HTTPError as exc:
            logger.exception("Document storage upload failed. object_key=%s status=%s", object_key, exc.code)
            raise DocumentStorageUploadError("Document upload failed.") from exc
        except URLError as exc:
            logger.exception("Document storage upload request failed. object_key=%s", object_key)
            raise DocumentStorageUploadError("Document upload failed.") from exc

    async def ensure_object_exists(self, *, object_key: str) -> None:
        try:
            await self._perform_request(method="HEAD", object_key=object_key)
        except HTTPError as exc:
            if exc.code == 404:
                raise DocumentStorageMissingObjectError("Document object not found.") from exc
            logger.exception("Document storage HEAD failed. object_key=%s status=%s", object_key, exc.code)
            raise DocumentStorageError("Document lookup failed.") from exc
        except URLError as exc:
            logger.exception("Document storage HEAD request failed. object_key=%s", object_key)
            raise DocumentStorageError("Document lookup failed.") from exc

    async def delete_object(self, *, object_key: str, missing_ok: bool = False) -> None:
        try:
            await self._perform_request(method="DELETE", object_key=object_key)
        except HTTPError as exc:
            if exc.code == 404 and missing_ok:
                return
            logger.exception("Document storage delete failed. object_key=%s status=%s", object_key, exc.code)
            raise DocumentStorageDeleteError("Document delete failed.") from exc
        except URLError as exc:
            logger.exception("Document storage delete request failed. object_key=%s", object_key)
            raise DocumentStorageDeleteError("Document delete failed.") from exc

    def build_presigned_download_url(self, *, object_key: str, expires_in_seconds: int) -> PresignedObjectUrl:
        if expires_in_seconds <= 0:
            raise DocumentStorageDownloadLinkError("Presigned URL TTL must be positive.")

        try:
            requested_at = _utc_now()
            expires_at = requested_at + timedelta(seconds=expires_in_seconds)
            request_url, uri, host = self._build_request_url(endpoint=self.public_endpoint, object_key=object_key)
            amz_date = requested_at.strftime("%Y%m%dT%H%M%SZ")
            datestamp = requested_at.strftime("%Y%m%d")
            credential_scope = f"{datestamp}/{self.region}/{_SERVICE_NAME}/aws4_request"
            query_parameters = [
                ("X-Amz-Algorithm", _AWS_ALGORITHM),
                ("X-Amz-Credential", f"{self.access_key}/{credential_scope}"),
                ("X-Amz-Date", amz_date),
                ("X-Amz-Expires", str(expires_in_seconds)),
                ("X-Amz-SignedHeaders", "host"),
            ]
            canonical_request = "\n".join(
                [
                    "GET",
                    uri,
                    _canonicalize_query(query_parameters),
                    f"host:{host}\n",
                    "host",
                    "UNSIGNED-PAYLOAD",
                ]
            )
            string_to_sign = "\n".join(
                [
                    _AWS_ALGORITHM,
                    amz_date,
                    credential_scope,
                    hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
                ]
            )
            signature = hmac.new(
                _derive_signing_key(self.secret_key, datestamp, self.region),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            query_parameters.append(("X-Amz-Signature", signature))
            return PresignedObjectUrl(
                url=f"{request_url}?{_canonicalize_query(query_parameters)}",
                expires_at=expires_at,
            )
        except DocumentStorageError:
            raise
        except Exception as exc:
            logger.exception("Document storage presign failed. object_key=%s", object_key)
            raise DocumentStorageDownloadLinkError("Document presign failed.") from exc


def get_document_storage() -> S3CompatibleDocumentStorage:
    public_endpoint = settings.document_storage_public_endpoint or settings.document_storage_endpoint
    return S3CompatibleDocumentStorage(
        endpoint=settings.document_storage_endpoint,
        public_endpoint=public_endpoint,
        bucket=settings.document_storage_bucket,
        access_key=settings.document_storage_access_key,
        secret_key=settings.document_storage_secret_key,
        region=settings.document_storage_region,
        timeout_seconds=settings.document_storage_timeout_seconds,
    )
