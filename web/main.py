import logging
import sys
import uvicorn
import asyncio # Added asyncio
import logging
import sys
import uvicorn
import asyncio
# Removed unused imports: json, Optional, ObjectId, bson_errors, HTTPException, llm_service, application_service, redis_client, ApplicationStatus, ApplicationDB
from fastapi import FastAPI, Depends, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse # Added RedirectResponse
from contextlib import asynccontextmanager

# Import config, db functions, routers, auth
from .config import settings
from shared import db
from . import redis_client # Import redis_client
# Import routers
from .routers import applications, links, users # Added users router
from .auth import authenticate_moderator
# Removed unused service imports

# Configure logging via dictionary
# Removed logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define logging configuration dictionary
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            # Example format: 2024-04-01 10:30:00 - bot.web.auth - DEBUG - authenticate_moderator called...
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr", # Output logs to stderr
        },
    },
    "loggers": {
        "": {  # Root logger configuration (now less important for this specific logger)
            "handlers": ["default"],
            "level": "INFO", # Can set root back to INFO if desired, as web.auth is explicit
            "propagate": False
        },
        "uvicorn.error": {
             "level": "INFO",
             "handlers": ["default"],
             "propagate": False
        },
        "uvicorn.access": {
             "level": "INFO",
             "handlers": ["default"],
             "propagate": False
        },
        "pymongo": {
             "level": "INFO",
             "handlers": ["default"],
             "propagate": False
        },
        "web.auth": { # Explicitly configure the auth logger
             "handlers": ["default"],
             "level": "DEBUG",
             "propagate": False # Don't pass messages up to the root logger
        }
    }
}


# Removed auto-moderation consumer task and related logic

# Async context manager for application lifespan events (startup/shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Application startup...")
    await db.connect_db() # Connect to MongoDB
    # Connect to Redis
    await redis_client.connect_redis()

    yield # Application runs here

    # Shutdown actions
    logger.info("Application shutdown...")
    # Disconnect from Redis
    await redis_client.disconnect_redis()
    await db.disconnect_db() # Disconnect from MongoDB

# Create FastAPI app instance without global dependency for docs
# Set docs_url=None and openapi_url=None to disable automatic generation
app = FastAPI(
    title="Application Moderation API",
    description="API for viewing and moderating user applications.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None, # Disable default /docs
    openapi_url=None # Disable default /openapi.json
# dependencies=[Depends(authenticate_moderator)] # REMOVED Global dependency
)

# --- Template and Static Files Setup ---
# Paths are relative to the WORKDIR (/app) inside the container
templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
# --- End Template and Static Files Setup ---


# Include the routers
app.include_router(links.router) # Include the new links router (usually handles /links)
app.include_router(users.router) # Include the new users router (handles /users, /users/broadcast)
app.include_router(applications.router, prefix="/applications") # Include applications under /applications

# Define protected route for OpenAPI schema
@app.get("/openapi.json", include_in_schema=False) # exclude from schema itself
async def get_open_api_endpoint(username: str = Depends(authenticate_moderator)):
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

# Define protected route for Swagger UI
@app.get("/docs", include_in_schema=False) # exclude from schema
async def custom_swagger_ui_html(username: str = Depends(authenticate_moderator)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json", # Point to our protected openapi endpoint
        title=app.title + " - Swagger UI",
    )

# Removed unused datetime import

# Root endpoint - Redirect to the links page
@app.get("/", response_class=RedirectResponse, tags=["Root"], name="read_root", dependencies=[Depends(authenticate_moderator)])
async def read_root(username: str = Depends(authenticate_moderator)): # Keep username dependency for auth
    logger.info(f"User {username} accessed root, redirecting to /links")
    # Redirect to the named route "list_links" which corresponds to GET /links
    return RedirectResponse(url="/links", status_code=302) # Use 302 Found for temporary redirect

# --- Main execution block (for running with uvicorn directly) ---
# Note: Usually you run FastAPI with `uvicorn web.main:app --reload`
# This block is mostly for potential direct execution or simpler debugging.
if __name__ == "__main__":
    logger.info(f"Starting Uvicorn server on {settings.web_app_host}:{settings.web_app_port}")
    uvicorn.run(
        "web.main:app",
        host=settings.web_app_host,
        port=settings.web_app_port,
        reload=True, # Enable auto-reload for development
        log_config=LOGGING_CONFIG # Use the dictionary config instead of log_level
    )
