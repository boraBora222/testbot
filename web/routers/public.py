import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from shared import db
from shared.models import WebsiteSubmissionDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["Public Website"])


def _validate_email(value: str) -> str:
    normalized_value = value.strip()
    if "@" not in normalized_value or "." not in normalized_value.split("@", 1)[-1]:
        raise ValueError("Invalid email format.")
    return normalized_value


class SubmissionResponse(BaseModel):
    submission_id: str


class RequestModalSubmissionRequest(BaseModel):
    locale: Literal["ru", "en"]
    page: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=2, max_length=120)
    company: Optional[str] = Field(default=None, max_length=200)
    email: str = Field(min_length=5, max_length=255)
    phone: str = Field(min_length=5, max_length=40)
    message: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class ContactSubmissionRequest(BaseModel):
    locale: Literal["ru", "en"]
    page: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    company: Optional[str] = Field(default=None, max_length=200)
    subject: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=2, max_length=4000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class CalculatorSubmissionRequest(BaseModel):
    locale: Literal["ru", "en"]
    page: str = Field(min_length=1, max_length=255)
    direction: Literal["buy", "sell"]
    amount: str = Field(min_length=1, max_length=40)
    network: str = Field(min_length=3, max_length=40)
    address: str = Field(min_length=10, max_length=120)
    name: str = Field(min_length=2, max_length=120)
    company: Optional[str] = Field(default=None, max_length=200)
    contact: str = Field(min_length=5, max_length=255)
    calculated_receive_amount: str = Field(min_length=1, max_length=40)
    calculated_fee_amount: str = Field(min_length=1, max_length=40)
    agreed: Literal[True]


async def _save_submission(submission: WebsiteSubmissionDB) -> SubmissionResponse:
    try:
        submission_id = await db.create_website_submission(submission)
    except Exception as exc:
        logger.exception(
            "Website submission persistence failed. source=%s page=%s locale=%s",
            submission.source,
            submission.page,
            submission.locale,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save website submission.",
        ) from exc

    logger.info(
        "Website submission created. source=%s submission_id=%s page=%s",
        submission.source,
        submission_id,
        submission.page,
    )
    return SubmissionResponse(submission_id=submission_id)


@router.post("/request-modal", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_request_modal(payload: RequestModalSubmissionRequest) -> SubmissionResponse:
    submission = WebsiteSubmissionDB(
        source="request_modal",
        locale=payload.locale,
        page=payload.page,
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        message=payload.message,
        payload={},
    )
    return await _save_submission(submission)


@router.post("/contacts", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_contacts(payload: ContactSubmissionRequest) -> SubmissionResponse:
    submission = WebsiteSubmissionDB(
        source="contacts",
        locale=payload.locale,
        page=payload.page,
        name=payload.name,
        company=payload.company,
        email=payload.email,
        subject=payload.subject,
        message=payload.message,
        payload={},
    )
    return await _save_submission(submission)


@router.post("/calculator", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_calculator(payload: CalculatorSubmissionRequest) -> SubmissionResponse:
    submission = WebsiteSubmissionDB(
        source="calculator",
        locale=payload.locale,
        page=payload.page,
        name=payload.name,
        company=payload.company,
        contact=payload.contact,
        payload={
            "direction": payload.direction,
            "amount": payload.amount,
            "network": payload.network,
            "address": payload.address,
            "calculated_receive_amount": payload.calculated_receive_amount,
            "calculated_fee_amount": payload.calculated_fee_amount,
            "agreed": payload.agreed,
        },
    )
    return await _save_submission(submission)
