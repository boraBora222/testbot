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


class MaterialContentType(str, Enum):
    """Supported material content types."""

    TEXT = "text"
    PHOTO = "photo"
    DOCUMENT = "document"