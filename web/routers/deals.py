import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from shared import db
from shared.models import WebUserDB
from shared.services import documents as document_service
from shared.types.enums import DealDocumentType
from web.auth import get_current_user
from web.models import DealDocumentDownloadResponse, DealDocumentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deals", tags=["Deals"])

DEAL_ACCESS_FORBIDDEN_MESSAGE = "You do not have access to this deal."
DEAL_DOCUMENT_NOT_FOUND_MESSAGE = "Deal document not found."


def _require_linked_exchange_user_id(current_user: WebUserDB) -> int:
    if current_user.linked_exchange_user_id is None:
        logger.error("Deals API rejected because web user is not linked. user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Current web account is not linked to an exchange user.",
        )
    return current_user.linked_exchange_user_id


def _serialize_deal_document(entry: dict) -> DealDocumentResponse:
    return DealDocumentResponse(
        id=entry["id"],
        type=entry["deal_doc_type"],
        file_name=entry["file_name"],
        file_size=entry["file_size"],
        created_at=entry["created_at"],
    )


async def _require_accessible_deal(deal_id: str, exchange_user_id: int, *, action: str) -> dict:
    deal = await db.get_order_for_user(deal_id, exchange_user_id)
    if deal is None:
        logger.warning("Deal document access denied. user_id=%s deal_id=%s", exchange_user_id, deal_id)
        document_service.audit_document_event(
            action=action,
            outcome="denied",
            scope="deal",
            user_id=exchange_user_id,
            deal_id=deal_id,
            reason="deal_access_denied",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEAL_ACCESS_FORBIDDEN_MESSAGE)
    return deal


async def _require_deal_document_in_scope(*, deal_id: str, document_id: str, owner_user_id: int) -> dict:
    document = await db.get_deal_document(deal_id, document_id, user_id=owner_user_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=DEAL_DOCUMENT_NOT_FOUND_MESSAGE)
    return document


@router.get("/{deal_id}/documents", response_model=list[DealDocumentResponse])
async def list_deal_documents(
    deal_id: str,
    current_user: WebUserDB = Depends(get_current_user),
) -> list[DealDocumentResponse]:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    deal = await _require_accessible_deal(deal_id, exchange_user_id, action="list")
    documents = await db.list_deal_documents(deal_id, user_id=deal["user_id"])
    return [_serialize_deal_document(document) for document in documents]


@router.post("/{deal_id}/documents", response_model=DealDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_deal_document(
    deal_id: str,
    document_type: DealDocumentType = Form(..., alias="type"),
    file: UploadFile = File(...),
    current_user: WebUserDB = Depends(get_current_user),
) -> DealDocumentResponse:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    deal = await _require_accessible_deal(deal_id, exchange_user_id, action="deal_link")
    try:
        stored_document = await document_service.store_deal_document_upload(
            user_id=deal["user_id"],
            username=deal.get("username"),
            first_name=None,
            deal_id=deal_id,
            deal_doc_type=document_type,
            upload=file,
        )
    except document_service.DealDocumentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (
        document_service.DealDocumentStorageUnavailableError,
        document_service.DealDocumentPersistenceError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    logger.info(
        "Deal document attached. deal_id=%s user_id=%s document_id=%s deal_doc_type=%s",
        deal_id,
        deal["user_id"],
        stored_document.document["id"],
        document_type.value,
    )
    return _serialize_deal_document(stored_document.document)


@router.get("/{deal_id}/documents/{document_id}/download", response_model=DealDocumentDownloadResponse)
async def get_deal_document_download_link(
    deal_id: str,
    document_id: str,
    current_user: WebUserDB = Depends(get_current_user),
) -> DealDocumentDownloadResponse:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    deal = await _require_accessible_deal(deal_id, exchange_user_id, action="download")
    document = await _require_deal_document_in_scope(
        deal_id=deal_id,
        document_id=document_id,
        owner_user_id=deal["user_id"],
    )
    try:
        download_link = await document_service.issue_deal_document_download_link(s3_key=document["s3_key"])
    except document_service.DealDocumentStoredFileMissingError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except document_service.DealDocumentDownloadUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    logger.info("Deal document download issued. deal_id=%s user_id=%s document_id=%s", deal_id, deal["user_id"], document_id)
    document_service.audit_document_event(
        action="download",
        outcome="success",
        scope="deal",
        user_id=deal["user_id"],
        deal_id=deal_id,
        document_id=document_id,
        deal_doc_type=document.get("deal_doc_type"),
        s3_key=document.get("s3_key"),
        file_name=document.get("file_name"),
    )
    return DealDocumentDownloadResponse(
        download_url=download_link.download_url,
        expires_at=download_link.expires_at,
    )
