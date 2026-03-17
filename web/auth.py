import secrets
import logging
import sys # Keep sys import just in case, or remove if not needed elsewhere
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from web.config import settings

# Initialize logger (still used for warning/info)
logger = logging.getLogger(__name__)

# Define the security scheme
security = HTTPBasic()

async def authenticate_moderator(credentials: HTTPBasicCredentials = Depends(security)):
    """
    FastAPI dependency to verify HTTP Basic Auth credentials for moderator access.

    Compares provided username and password against configured moderator credentials
    using a timing-attack resistant method.

    Args:
        credentials: The HTTP Basic credentials provided by the client.

    Raises:
        HTTPException (401 Unauthorized): If credentials are invalid or missing.

    Returns:
        str: The authenticated username if credentials are valid.
    """
    # Removed print statement
    # print("!!! DEBUG: authenticate_moderator called !!!", file=sys.stderr)
    # sys.stderr.flush()

    correct_username = secrets.compare_digest(credentials.username, settings.moderator_username)
    correct_password = secrets.compare_digest(credentials.password, settings.moderator_password)

    if not (correct_username and correct_password):
        logger.warning(f"Failed authentication attempt for user: {credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    logger.info(f"User '{credentials.username}' authenticated successfully.")
    return credentials.username # Return username upon successful authentication 