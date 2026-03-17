from typing import Optional, Dict, Any, List, Annotated # Import Annotated
from pydantic import BaseModel, Field, BeforeValidator # Import BeforeValidator
from datetime import datetime
from bson import ObjectId # Import ObjectId

# Import shared models and enums
from shared.types.enums import ApplicationStatus
# We need ApplicationDB to potentially inherit or reuse fields
# but avoid circular dependency if ApplicationDB imports something from web
# Let's define the response model explicitly for now.

class RejectReason(BaseModel):
    """Pydantic model for the request body when rejecting an application."""
    reason: str = Field(..., min_length=1, description="Reason for rejection")

# --- Custom ObjectId Type using Pydantic v2 Annotated --- 

# Define the validation function directly
def validate_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    if ObjectId.is_valid(str(v)):
        return str(v)
    raise ValueError(f"Invalid ObjectId: {v}")

# Use Annotated to combine the base type (str) with the validator
# Pydantic can often generate a basic string schema automatically for this
PyObjectId = Annotated[
    str, # The type represented in Python
    BeforeValidator(validate_object_id), # Apply validation before Pydantic uses the value
    # We can add more constraints or schema modifications here if needed
    # e.g., Field(..., description=..., example=...) inside Annotated
]

class ApplicationResponse(BaseModel):
    """Pydantic model for representing an application in API responses."""
    # Use the new Annotated PyObjectId type
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
        populate_by_name = True # Allow population by field name (e.g., _id)
        json_encoders = {
            ObjectId: str # Ensure ObjectId is serialized to string
        }
        # If using Pydantic v2, arbitrary_types_allowed=True might be needed for ObjectId
        # Or define a custom type like PyObjectId above
        # arbitrary_types_allowed = True # Uncomment if using raw ObjectId field and Pydantic v2

# Model for list response
class ApplicationListResponse(BaseModel):
    applications: List[ApplicationResponse] 