from decimal import Decimal
from typing import Any, Dict, Optional, Literal
import uuid
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from datetime import datetime, timezone
from .security_settings import utc_now, validate_whitelist_address_record
from .types.enums import (
    AddressSource,
    ApplicationStatus,
    ClientDocumentType,
    DealDocumentType,
    DraftSource,
    DraftStep,
    ExchangeType,
    MaterialContentType,
    OrderCreatedFrom,
    OrderStatus,
    VerificationLevel,
    WhitelistAddressStatus,
)

# Define an Enum for application status later if needed
# from enum import Enum
# class ApplicationStatus(str, Enum):
#     PENDING = "pending"
#     APPROVED = "approved"
#     REJECTED = "rejected"

class ApplicationData(BaseModel):
    """Pydantic model to store questionnaire answers temporarily in FSM context."""
    # We can store answers in a dictionary
    # Use specific fields if you know the questions beforehand
    question1: Optional[str] = None
    question2: Optional[str] = None
    question3: Optional[str] = None
    # Add fields corresponding to the states/questions

    # You might add other useful info collected during the process
    # e.g., message_ids to edit later, etc.

# We can also define the model for the data stored in MongoDB
# This helps ensure consistency and provides validation
class ApplicationDB(BaseModel):
    """Pydantic model representing an application document in MongoDB."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    answers: Dict[str, Any] # Store answers from ApplicationData here
    status: ApplicationStatus = ApplicationStatus.PENDING # Use Enum and set default
    moderation_comment: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    moderated_at: Optional[datetime] = None
    # Fields for moderation type and auto-moderation result
    moderation_type: Optional[Literal["manual", "auto"]] = Field(default=None)
    auto_moderation_result: Optional[dict] = Field(default=None) # Store LLM response here
    # Fields for notification status
    notified: bool = False
    notification_error: Optional[str] = None

    # If using MongoDB's ObjectId:
    # from pydantic import Field
    # from bson import ObjectId
    # id: Optional[ObjectId] = Field(alias="_id", default=None)

class LinkDB(BaseModel):
    """Pydantic model representing a submitted link/material document in MongoDB."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    text: Optional[str] = None # Text content if content_type is 'text'
    telegram_file_id: Optional[str] = None # File ID if content_type is 'photo'
    caption: Optional[str] = None # Caption for photo/file
    content_type: Literal['text', 'photo'] = 'text' # Type of submitted content
    # Optional fields primarily for documents treated as photos
    file_name: Optional[str] = None # Original file name for documents
    mime_type: Optional[str] = None # Mime type for documents
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Use timezone aware datetime


class BotUser(BaseModel):
    """Pydantic model representing a user interacting with the bot."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: int # Telegram User ID (unique index)
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None # Telegram Last Name (optional)
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp of first interaction
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp of last interaction


class BannedUser(BaseModel):
    """Pydantic model representing a banned Telegram user."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    reason: Optional[str] = None
    banned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    banned_by: Optional[str] = None

class NotificationEventsPreferences(BaseModel):
    """Per-event notification toggles for a client profile."""

    model_config = ConfigDict(extra="forbid")

    order_created: StrictBool
    order_status_changed: StrictBool
    support_reply: StrictBool
    limit_warning: StrictBool


class NotificationPreferences(BaseModel):
    """User-controlled notification channel and event settings."""

    model_config = ConfigDict(extra="forbid")

    telegram_enabled: StrictBool
    email_enabled: StrictBool
    events: NotificationEventsPreferences


def build_default_notification_preferences() -> NotificationPreferences:
    return NotificationPreferences(
        telegram_enabled=True,
        email_enabled=True,
        events=NotificationEventsPreferences(
            order_created=True,
            order_status_changed=True,
            support_reply=True,
            limit_warning=True,
        ),
    )


class ExchangeUserDB(BaseModel):
    """MongoDB document for Telegram users in the demo exchange flow."""
    model_config = ConfigDict(populate_by_name=True)

    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_banned: bool = False
    notification_preferences: NotificationPreferences
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LimitQuotaDB(BaseModel):
    """MongoDB document storing user limit quotas and usage counters."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    verification_level: VerificationLevel
    daily_limit: Decimal = Field(gt=0)
    daily_used: Decimal = Field(ge=0)
    daily_reset_at: datetime
    monthly_limit: Decimal = Field(gt=0)
    monthly_used: Decimal = Field(ge=0)
    monthly_reset_at: datetime
    updated_at: datetime = Field(default_factory=utc_now)

class LimitQuotaHistoryDB(BaseModel):
    """MongoDB audit document for admin changes to user quotas."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    changed_by: str = Field(min_length=1)
    field: str = Field(min_length=1)
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("changed_by", "field", "reason")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized

class WhitelistAddressDB(BaseModel):
    """MongoDB document for user payout addresses awaiting moderation."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: f"wla_{uuid.uuid4().hex}")
    user_id: int
    network: str
    address: str
    address_normalized: Optional[str] = None
    label: str = Field(min_length=1, max_length=120)
    status: WhitelistAddressStatus = WhitelistAddressStatus.PENDING
    rejection_reason: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("label")
    @classmethod
    def _normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Whitelist label is required.")
        return normalized

    @model_validator(mode="after")
    def _normalize_identity(self) -> "WhitelistAddressDB":
        canonical_network, normalized_address = validate_whitelist_address_record(
            self.network,
            self.address,
            self.address_normalized,
        )
        self.network = canonical_network
        self.address = self.address.strip()
        self.address_normalized = normalized_address
        return self

class OrderDB(BaseModel):
    """MongoDB document for demo exchange orders."""
    model_config = ConfigDict(populate_by_name=True)

    order_id: str
    user_id: int
    username: Optional[str] = None
    exchange_type: ExchangeType
    from_currency: str
    to_currency: str
    amount: Decimal
    network: str
    address: str
    address_source: AddressSource = AddressSource.MANUAL
    whitelist_address_id: Optional[str] = None
    wallet_address: Optional[str] = None
    wallet_network: Optional[str] = None
    rate: Decimal
    fee_percent: Decimal
    fee_amount: Decimal
    receive_amount: Decimal
    status: OrderStatus = OrderStatus.NEW
    created_from: OrderCreatedFrom = OrderCreatedFrom.MANUAL
    source_order_id: Optional[str] = None
    source_draft_id: Optional[str] = None
    is_demo: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _finalize_wallet_provenance(self) -> "OrderDB":
        if self.address_source == AddressSource.WHITELIST and not self.whitelist_address_id:
            raise ValueError("whitelist_address_id is required when address_source is whitelist.")
        if self.address_source == AddressSource.MANUAL and self.whitelist_address_id is not None:
            raise ValueError("whitelist_address_id must be empty when address_source is manual.")

        self.network = self.network.strip()
        self.address = self.address.strip()
        self.wallet_address = self.wallet_address.strip() if self.wallet_address else self.address
        self.wallet_network = self.wallet_network.strip() if self.wallet_network else self.network
        return self

class MaterialDB(BaseModel):
    """MongoDB document for generic user materials."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: f"mat_{uuid.uuid4().hex}")
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    content_type: MaterialContentType
    client_doc_type: Optional[ClientDocumentType] = None
    deal_doc_type: Optional[DealDocumentType] = None
    deal_id: Optional[str] = None
    text: Optional[str] = None
    telegram_file_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("telegram_file_id", "file_id"),
    )
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = Field(default=None, ge=0)
    s3_key: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def file_id(self) -> Optional[str]:
        return self.telegram_file_id

    @field_validator("deal_id", "telegram_file_id", "file_name", "mime_type", "s3_key")
    @classmethod
    def _strip_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_document_shape(self) -> "MaterialDB":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at.")

        document_types = {
            MaterialContentType.CLIENT_DOC,
            MaterialContentType.DEAL_DOC,
        }
        if self.content_type not in document_types:
            if self.client_doc_type is not None or self.deal_doc_type is not None or self.deal_id is not None or self.s3_key is not None:
                raise ValueError("Document-specific fields are only allowed for CLIENT_DOC and DEAL_DOC records.")
            return self

        if not self.file_name:
            raise ValueError("file_name is required for document records.")
        if not self.mime_type:
            raise ValueError("mime_type is required for document records.")
        if self.file_size is None:
            raise ValueError("file_size is required for document records.")
        if not self.s3_key:
            raise ValueError("s3_key is required for document records.")

        if self.content_type == MaterialContentType.CLIENT_DOC:
            if self.client_doc_type is None:
                raise ValueError("client_doc_type is required for CLIENT_DOC records.")
            if self.deal_doc_type is not None:
                raise ValueError("deal_doc_type must be empty for CLIENT_DOC records.")
            if self.deal_id is not None:
                raise ValueError("deal_id must be empty for CLIENT_DOC records.")
            return self

        if self.deal_doc_type is None:
            raise ValueError("deal_doc_type is required for DEAL_DOC records.")
        if self.client_doc_type is not None:
            raise ValueError("client_doc_type must be empty for DEAL_DOC records.")
        if self.deal_id is None:
            raise ValueError("deal_id is required for DEAL_DOC records.")
        return self

class SupportMessageDB(BaseModel):
    """MongoDB document for support messages."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    username: Optional[str] = None
    text: str
    has_attachment: bool = False
    is_processed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class WebsiteSubmissionDB(BaseModel):
    """MongoDB document for public website submissions."""
    model_config = ConfigDict(populate_by_name=True)

    source: Literal["request_modal", "contacts", "calculator"]
    locale: Literal["ru", "en"]
    page: str
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    contact: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["new"] = "new"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusMeta(BaseModel):
    """Derived explanation for the current order status."""

    title: str
    reason: str
    eta_text: Optional[str] = None
    next_step: Optional[str] = None
    is_terminal: bool


class OrderTimelineStep(BaseModel):
    """Derived timeline item for order progress UI."""

    key: str
    label: str
    status: Literal["pending", "active", "completed"]
    timestamp: Optional[datetime] = None


class OrderDraftDB(BaseModel):
    """MongoDB document for a saved order draft."""
    model_config = ConfigDict(populate_by_name=True)

    draft_id: str
    owner_channel: Literal["telegram", "web"]
    owner_id: str
    source: DraftSource
    source_order_id: Optional[str] = None
    exchange_type: Optional[ExchangeType] = None
    from_currency: Optional[str] = None
    to_currency: Optional[str] = None
    amount: Optional[Decimal] = None
    network: Optional[str] = None
    address: Optional[str] = None
    use_whitelist: Optional[bool] = None
    current_step: DraftStep
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

class WebUserDB(BaseModel):
    """Website user document for email/password authentication."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    email: str
    password_hash: str
    is_active: bool = True
    email_verified: bool = False
    name: str = ""
    company: str = ""
    linked_exchange_user_id: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None
    email_verification_code_hash: Optional[str] = None
    email_verification_code_expires_at: Optional[datetime] = None
    email_verification_attempts: int = 0
    password_reset_code_hash: Optional[str] = None
    password_reset_code_expires_at: Optional[datetime] = None
    password_reset_attempts: int = 0

class AuthSessionDB(BaseModel):
    """Authentication session document for session-based auth."""
    model_config = ConfigDict(populate_by_name=True)

    session_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
