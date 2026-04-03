from enum import Enum

class ApplicationStatus(str, Enum):
    """Possible statuses for a user application."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected" 


class ExchangeType(str, Enum):
    """Supported exchange directions for the demo bot."""

    CRYPTO_TO_FIAT = "crypto_to_fiat"
    FIAT_TO_CRYPTO = "fiat_to_crypto"
    CRYPTO_TO_CRYPTO = "crypto_to_crypto"


class OrderStatus(str, Enum):
    """Supported order statuses for the demo bot."""

    NEW = "new"
    PROCESSING = "processing"
    WAITING_PAYMENT = "waiting_payment"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderListFilter(str, Enum):
    """Product filters available for order lists."""

    ALL = "all"
    ACTIVE = "active"
    NEW = "new"
    WAITING_PAYMENT = "waiting_payment"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DraftSource(str, Enum):
    """Source that initiated the draft."""

    MANUAL = "manual"
    REPEAT = "repeat"


class DraftStep(str, Enum):
    """Current step saved in the draft."""

    AMOUNT = "amount"
    ADDRESS = "address"
    CONFIRM = "confirm"


class OrderCreatedFrom(str, Enum):
    """Origin of a created order."""

    MANUAL = "manual"
    REPEAT = "repeat"
    DRAFT_SUBMIT = "draft_submit"


class AddressSource(str, Enum):
    """Origin of the payout wallet address attached to an order."""

    WHITELIST = "whitelist"
    MANUAL = "manual"


class VerificationLevel(str, Enum):
    """Verification levels used by profile quota settings."""

    BASIC = "basic"
    EXTENDED = "extended"
    CORPORATE = "corporate"


class WhitelistAddressStatus(str, Enum):
    """Supported moderation states for whitelist addresses."""

    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"


class MaterialContentType(str, Enum):
    """Supported material content types."""

    TEXT = "text"
    PHOTO = "photo"
    DOCUMENT = "document"
    CLIENT_DOC = "client_doc"
    DEAL_DOC = "deal_doc"


class ClientDocumentType(str, Enum):
    """Supported client document types for profile uploads."""

    INN = "inn"
    OGRN = "ogrn"
    CHARTER = "charter"
    PROTOCOL = "protocol"
    DIRECTOR_PASSPORT = "director_passport"
    EGRUL_EXTRACT = "egrul_extract"
    BANK_DETAILS = "bank_details"
    OTHER = "other"


class DealDocumentType(str, Enum):
    """Supported prepared document types attached to a deal."""

    CONTRACT = "contract"
    ACT = "act"
    CONFIRMATION = "confirmation"
    OTHER = "other"
