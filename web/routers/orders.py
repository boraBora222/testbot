import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from shared import db
from shared.models import WebUserDB
from shared.services.order_lifecycle import (
    build_order_detail_payload,
    build_order_draft,
    build_repeat_seed,
    get_status_filter_values,
)
from shared.services.security_settings import (
    LimitQuotaNotConfiguredError,
    WhitelistApprovalRequiredError,
    create_order_with_security_checks,
)
from shared.types.enums import OrderCreatedFrom, OrderListFilter
from web.auth import get_current_user
from web.models import (
    CurrentOrderDraftResponse,
    OrderListResponse,
    OrderResponse,
    RepeatOrderResponse,
    SimpleSuccessResponse,
    UpsertOrderDraftRequest,
)
from web.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Orders"])


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _serialize_order_response(payload: dict) -> OrderResponse:
    return OrderResponse(
        order_id=payload["order_id"],
        user_id=payload["user_id"],
        username=payload.get("username"),
        exchange_type=payload["exchange_type"],
        from_currency=payload["from_currency"],
        to_currency=payload["to_currency"],
        amount=_format_decimal(payload["amount"]),
        network=payload["network"],
        address=payload["address"],
        address_source=payload.get("address_source"),
        whitelist_address_id=payload.get("whitelist_address_id"),
        wallet_address=payload.get("wallet_address"),
        wallet_network=payload.get("wallet_network"),
        rate=_format_decimal(payload["rate"]),
        fee_percent=_format_decimal(payload["fee_percent"]),
        fee_amount=_format_decimal(payload["fee_amount"]),
        receive_amount=_format_decimal(payload["receive_amount"]),
        status=payload["status"],
        created_from=payload["created_from"],
        source_order_id=payload.get("source_order_id"),
        source_draft_id=payload.get("source_draft_id"),
        is_demo=payload["is_demo"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        status_meta=payload["status_meta"],
        can_repeat=payload["can_repeat"],
        timeline=payload.get("timeline", []),
        available_actions=payload.get("available_actions", []),
        warnings=payload.get("warnings", []),
    )


def _serialize_draft_response(draft: dict) -> CurrentOrderDraftResponse:
    amount = draft.get("amount")
    return CurrentOrderDraftResponse(
        draft_id=draft["draft_id"],
        owner_channel=draft["owner_channel"],
        owner_id=draft["owner_id"],
        source=draft["source"],
        source_order_id=draft.get("source_order_id"),
        exchange_type=draft.get("exchange_type"),
        from_currency=draft.get("from_currency"),
        to_currency=draft.get("to_currency"),
        amount=_format_decimal(amount) if amount is not None else None,
        network=draft.get("network"),
        address=draft.get("address"),
        use_whitelist=draft.get("use_whitelist"),
        current_step=draft["current_step"],
        schema_version=draft["schema_version"],
        created_at=draft["created_at"],
        updated_at=draft["updated_at"],
        expires_at=draft.get("expires_at"),
    )


def _require_linked_exchange_user_id(current_user: WebUserDB) -> int:
    if current_user.linked_exchange_user_id is None:
        logger.error("Orders API rejected because web user is not linked. user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Current web account is not linked to an exchange user.",
        )
    return current_user.linked_exchange_user_id


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    status_filter: OrderListFilter = Query(default=OrderListFilter.ALL, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_user: WebUserDB = Depends(get_current_user),
) -> OrderListResponse:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    statuses = get_status_filter_values(status_filter)
    orders, total = await db.list_orders_for_user(
        exchange_user_id,
        page=page,
        page_size=page_size,
        statuses=list(statuses) if statuses else None,
    )
    serialized_items = [
        _serialize_order_response(build_order_detail_payload(order))
        for order in orders
    ]
    return OrderListResponse(
        items=serialized_items,
        total=total,
        page=page,
        page_size=page_size,
        status=status_filter,
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, current_user: WebUserDB = Depends(get_current_user)) -> OrderResponse:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    order = await db.get_order_for_user(order_id, exchange_user_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return _serialize_order_response(build_order_detail_payload(order))


@router.post("/orders/{order_id}/repeat", response_model=RepeatOrderResponse)
async def repeat_order(order_id: str, current_user: WebUserDB = Depends(get_current_user)) -> RepeatOrderResponse:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    order = await db.get_order_for_user(order_id, exchange_user_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return RepeatOrderResponse(prefill_payload=build_repeat_seed(order))


@router.get("/order-drafts/current", response_model=CurrentOrderDraftResponse)
async def get_current_order_draft(current_user: WebUserDB = Depends(get_current_user)) -> CurrentOrderDraftResponse:
    draft = await db.get_current_order_draft("web", current_user.id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return _serialize_draft_response(draft)


@router.put("/order-drafts/current", response_model=CurrentOrderDraftResponse)
async def upsert_current_order_draft(
    payload: UpsertOrderDraftRequest,
    current_user: WebUserDB = Depends(get_current_user),
) -> CurrentOrderDraftResponse:
    existing_draft = await db.get_current_order_draft("web", current_user.id)
    draft = build_order_draft(
        owner_channel="web",
        owner_id=current_user.id,
        payload=payload.model_dump(),
        source=payload.source,
        current_step=payload.current_step,
        source_order_id=payload.source_order_id,
        draft_id=existing_draft["draft_id"] if existing_draft is not None else None,
        created_at=existing_draft["created_at"] if existing_draft is not None else None,
    )
    saved_draft = await db.create_or_replace_order_draft(draft)
    return _serialize_draft_response(saved_draft.model_dump())


@router.delete("/order-drafts/current", response_model=SimpleSuccessResponse)
async def delete_current_order_draft(current_user: WebUserDB = Depends(get_current_user)) -> SimpleSuccessResponse:
    deleted = await db.delete_order_draft("web", current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return SimpleSuccessResponse(message="Draft deleted successfully.")


@router.post("/order-drafts/current/submit", response_model=OrderResponse)
async def submit_current_order_draft(current_user: WebUserDB = Depends(get_current_user)) -> OrderResponse:
    exchange_user_id = _require_linked_exchange_user_id(current_user)
    draft = await db.get_current_order_draft("web", current_user.id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")

    try:
        order, warnings = await create_order_with_security_checks(
            user_id=exchange_user_id,
            username=current_user.email,
            payload=draft,
            is_demo=settings.demo_mode,
            created_from=OrderCreatedFrom.DRAFT_SUBMIT,
            source_order_id=draft.get("source_order_id"),
            source_draft_id=draft["draft_id"],
        )
    except WhitelistApprovalRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LimitQuotaNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await db.delete_order_draft("web", current_user.id)
    response_payload = build_order_detail_payload(order.model_dump())
    response_payload["warnings"] = warnings
    return _serialize_order_response(response_payload)
