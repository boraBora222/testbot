from typing import Dict, Any, Optional, Literal # Added Literal
from pydantic import BaseModel, Field
from datetime import datetime, timezone # Added timezone
from .types.enums import ApplicationStatus # Import the enum

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

    class Config:
        # Allow population by field name, not just alias (for reading from DB)
        populate_by_name = True
        # Configuration for MongoDB ObjectId serialization if used
        # json_encoders = {
        #     ObjectId: str
        # }

class LinkDB(BaseModel):
    """Pydantic model representing a submitted link/material document in MongoDB."""
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

    class Config:
        populate_by_name = True


class BotUser(BaseModel):
    """Pydantic model representing a user interacting with the bot."""
    user_id: int # Telegram User ID (unique index)
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None # Telegram Last Name (optional)
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp of first interaction
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp of last interaction

    class Config:
        populate_by_name = True
        # Consider adding collection_name if you manage collections via models
        # collection_name = "bot_users"


class BannedUser(BaseModel):
    """Pydantic model representing a banned Telegram user."""
    user_id: int
    reason: Optional[str] = None
    banned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    banned_by: Optional[str] = None

    class Config:
        populate_by_name = True