from enum import Enum

class ApplicationStatus(str, Enum):
    """Possible statuses for a user application."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected" 