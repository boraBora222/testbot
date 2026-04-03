import re
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from shared.types.enums import (
    ApplicationStatus,
    ClientDocumentType,
    DealDocumentType,
    DraftSource,
    DraftStep,
    ExchangeType,
    OrderListFilter,
    OrderStatus,
    VerificationLevel,
    WhitelistAddressStatus,
    AddressSource,
)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_object_id(value: Any) -> str:
    if isinstance(value, ObjectId):
        return str(value)
    if ObjectId.is_valid(str(value)):
        return str(value)
    raise ValueError(f"Invalid ObjectId: {value}")


def normalize_email(value: str) -> str:
    normalized_value = value.strip().lower()
    if not EMAIL_REGEX.match(normalized_value):
        raise ValueError("Invalid email format")
    return normalized_value


PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]


class RejectReason(BaseModel):
    """Pydantic model for the request body when rejecting an application."""

    reason: str = Field(..., min_length=1, description="Reason for rejection")


class ApplicationResponse(BaseModel):
    """Pydantic model for representing an application in API responses."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: PyObjectId = Field(alias="_id", description="Application MongoDB ObjectId")
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    answers: Dict[str, Any]
    status: ApplicationStatus
    moderation_comment: Optional[str] = None
    submitted_at: datetime
    moderated_at: Optional[datetime] = None

class ApplicationListResponse(BaseModel):
    applications: List[ApplicationResponse]


class RegisterRequest(BaseModel):
    email: str
    password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class SendVerificationCodeRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class VerifyEmailRequest(BaseModel):
    email: str
    code: str = Field(min_length=1, max_length=32)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class RequestPasswordResetRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    email: str
    code: str = Field(min_length=1, max_length=32)
    new_password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class AuthUserResponse(BaseModel):
    id: str
    email: str
    email_verified: bool
    is_active: bool
    name: str = ""
    company: str = ""


class SimpleSuccessResponse(BaseModel):
    success: bool = True
    message: str


class StatusMetaResponse(BaseModel):
    title: str
    reason: str
    eta_text: Optional[str] = None
    next_step: Optional[str] = None
    is_terminal: bool


class OrderTimelineStepResponse(BaseModel):
    key: str
    label: str
    status: str
    timestamp: Optional[datetime] = None


class OrderResponse(BaseModel):
    order_id: str
    user_id: int
    username: Optional[str] = None
    exchange_type: ExchangeType
    from_currency: str
    to_currency: str
    amount: str
    network: str
    address: str
    address_source: Optional[AddressSource] = None
    whitelist_address_id: Optional[str] = None
    wallet_address: Optional[str] = None
    wallet_network: Optional[str] = None
    rate: str
    fee_percent: str
    fee_amount: str
    receive_amount: str
    status: OrderStatus
    created_from: str
    source_order_id: Optional[str] = None
    source_draft_id: Optional[str] = None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    status_meta: StatusMetaResponse
    can_repeat: bool
    timeline: list[OrderTimelineStepResponse] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    status: OrderListFilter


class RepeatOrderResponse(BaseModel):
    prefill_payload: dict[str, Any]


class CurrentOrderDraftResponse(BaseModel):
    draft_id: str
    owner_channel: str
    owner_id: str
    source: DraftSource
    source_order_id: Optional[str] = None
    exchange_type: Optional[ExchangeType] = None
    from_currency: Optional[str] = None
    to_currency: Optional[str] = None
    amount: Optional[str] = None
    network: Optional[str] = None
    address: Optional[str] = None
    use_whitelist: Optional[bool] = None
    current_step: DraftStep
    schema_version: int
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None


class UpsertOrderDraftRequest(BaseModel):
    source: DraftSource
    source_order_id: Optional[str] = None
    exchange_type: ExchangeType
    from_currency: str = Field(min_length=1)
    to_currency: str = Field(min_length=1)
    amount: str = Field(min_length=1)
    network: str = Field(min_length=1)
    address: str = Field(min_length=1)
    use_whitelist: Optional[bool] = None
    current_step: DraftStep = DraftStep.CONFIRM


class ProfileLimitsResponse(BaseModel):
    verification_level: VerificationLevel
    daily_limit: str
    daily_used: str
    daily_remaining: str
    daily_reset_at: datetime
    monthly_limit: str
    monthly_used: str
    monthly_remaining: str
    monthly_reset_at: datetime
    updated_at: datetime


class ProfileDocumentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: ClientDocumentType
    file_name: str = Field(serialization_alias="fileName")
    file_size: int = Field(serialization_alias="fileSize")
    created_at: datetime = Field(serialization_alias="createdAt")


class ProfileDocumentDownloadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    download_url: str = Field(serialization_alias="downloadUrl")
    expires_at: datetime = Field(serialization_alias="expiresAt")


class DealDocumentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: DealDocumentType
    file_name: str = Field(serialization_alias="fileName")
    file_size: int = Field(serialization_alias="fileSize")
    created_at: datetime = Field(serialization_alias="createdAt")


class DealDocumentDownloadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    download_url: str = Field(serialization_alias="downloadUrl")
    expires_at: datetime = Field(serialization_alias="expiresAt")


class WhitelistAddressResponse(BaseModel):
    id: str
    network: str
    address: str
    label: str
    status: WhitelistAddressStatus
    rejection_reason: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CreateWhitelistAddressRequest(BaseModel):
    network: str = Field(min_length=1)
    address: str = Field(min_length=1)
    label: str = Field(min_length=1, max_length=120)

    @field_validator("network", "address", "label")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class UpdateWhitelistAddressLabelRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Whitelist label is required.")
        return normalized
