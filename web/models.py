import re
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field, field_validator

from shared.types.enums import ApplicationStatus

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

    id: PyObjectId = Field(alias="_id", description="Application MongoDB ObjectId")
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    answers: Dict[str, Any]
    status: ApplicationStatus
    moderation_comment: Optional[str] = None
    submitted_at: datetime
    moderated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}


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