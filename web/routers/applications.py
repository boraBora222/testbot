import logging
# Removed json import, handled in service
from typing import List, Optional
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Path, Form, Request # Added Request
from fastapi.responses import HTMLResponse # Added HTMLResponse
from fastapi.templating import Jinja2Templates # Added Jinja2Templates

# Import shared DB functions, models, and enums
from shared import db # Keep db import for get_applications_by_status
from shared.types.enums import ApplicationStatus
from shared.models import ApplicationDB # Import the DB model for type hints in DB functions

# Import API-specific models, config and auth
# Removed RejectReason
from ..models import ApplicationResponse, PyObjectId
# Removed settings import, not needed directly here anymore
from ..auth import authenticate_moderator # Import the authentication dependency
# Import the new application service
from ..services import application_service

logger = logging.getLogger(__name__)

# Removed Redis client setup - handled in service/redis_client.py

# Removed settings import, not needed directly here anymore
from ..auth import authenticate_moderator # Import the authentication dependency
# Import the new application service
from ..services import application_service

logger = logging.getLogger(__name__)

# Templates directory (relative to where main.py runs from, assuming project root)
templates = Jinja2Templates(directory="reply_bot/web/templates")

# Create API router with authentication dependency
# REMOVED prefix="/api/applications" - it will be set in main.py
router = APIRouter(
    tags=["Applications"], # Tag for OpenAPI documentation
    dependencies=[Depends(authenticate_moderator)] # Add authentication dependency here
)

# --- HTML Page Endpoint ---
@router.get("/", response_class=HTMLResponse, name="list_applications_page")
async def get_applications_page(request: Request):
    """Serves the HTML page displaying the list of applications."""
    try:
        # Fetch ALL applications from the database using the shared db function
        all_applications = await db.get_all_applications(sort_field="submitted_at", sort_order=-1)
        logger.info(f"Fetched {len(all_applications)} total applications for page rendering.")
    except Exception as e:
        logger.exception(f"Failed to fetch applications for page rendering: {e}")
        all_applications = [] # Return empty list on error

    # Render the applications.html template
    return templates.TemplateResponse(
        "applications.html", # Use the renamed template
        {
            "request": request,
            "applications": all_applications,
            "ApplicationStatus": ApplicationStatus, # Pass enum for use in template
            "page_title": "Заявки пользователей" # Set page title
        }
    )

# --- API Endpoints ---

@router.get(
    "/api", # Changed path to /api
    response_model=List[ApplicationResponse],
    summary="Get Applications by Status (API)"
)
async def get_applications_api( # Renamed function to avoid conflict
    status_filter: ApplicationStatus = Query(
        ApplicationStatus.PENDING, 
        description="Filter applications by status"
    )
):
    """
    Retrieve a list of applications, filtered by their status.
    Defaults to fetching applications with a 'pending' status.
    """
    logger.info(f"Fetching applications with status: {status_filter.value}")
    try:
        # Fetch raw dicts from DB (get_applications_by_status now returns list[dict])
        applications_raw: List[dict] = await db.get_applications_by_status(status_filter)
        
        # Convert raw dicts to response models using list comprehension
        # Pydantic will validate each dict against ApplicationResponse
        response_list = [ApplicationResponse(**app_data) for app_data in applications_raw]
        
        logger.info(f"Found {len(response_list)} applications with status {status_filter.value}")
        return response_list

    except Exception as e:
        logger.exception(f"Error processing applications: {e}") # Log the actual processing error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            # Provide a more generic error message to the client
            detail="An error occurred while fetching applications.",
        )

@router.post(
    "/api/{application_id}/approve", # Changed path to /api/...
    status_code=status.HTTP_204_NO_CONTENT, # Return 204 on success
    summary="Approve an Application (API)"
)
async def approve_application_api(application_id: PyObjectId = Path(..., description="The MongoDB ObjectId of the application to approve")): # Renamed function
    """
    Mark an application status as 'approved' using the application service.
    """
    logger.info(f"Attempting to manually approve application ID: {application_id}")
    try:
        success = await application_service.approve_application(
            application_id_str=str(application_id),
            moderator_type="manual" # Manual action from API
        )
        if not success:
            logger.warning(f"Failed to approve application {application_id}. Service returned False (not found or not modified).")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application with id {application_id} not found or could not be approved."
            )
        logger.info(f"Successfully approved application {application_id} via manual API call.")
        # No return needed for 204
    except Exception as e:
        logger.exception(f"Unexpected error during manual approval of application {application_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during application approval."
        )

@router.post(
    "/api/{application_id}/reject", # Changed path to /api/...
    status_code=status.HTTP_204_NO_CONTENT, # Return 204 on success
    summary="Reject an Application (API)"
)
async def reject_application_api( # Renamed function
    application_id: PyObjectId = Path(..., description="The MongoDB ObjectId of the application to reject"),
    # Accept reason from form data, make it optional
    reason: Optional[str] = Form(None, description="Optional reason for rejection provided via form")
):
    """
    Mark an application status as 'rejected' using the application service,
    recording the optional reason from the form.
    """
    rejection_reason = reason if reason else "Rejected by moderator." # Provide a default reason if none given
    logger.info(f"Attempting to manually reject application ID: {application_id} with reason: {rejection_reason}")

    try:
        success = await application_service.reject_application(
            application_id_str=str(application_id),
            reason=rejection_reason,
            moderator_type="manual" # Manual action from API
        )
        if not success:
            logger.warning(f"Failed to reject application {application_id}. Service returned False (not found or not modified).")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application with id {application_id} not found or could not be rejected."
            )
        logger.info(f"Successfully rejected application {application_id} via manual API call.")
        # No return needed for 204
    except Exception as e:
        logger.exception(f"Unexpected error during manual rejection of application {application_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during application rejection."
        )
