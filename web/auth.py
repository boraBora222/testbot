import hashlib
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import HashingError, InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from shared import db
from shared.models import AuthSessionDB, WebUserDB
from web.config import settings
from web.models import AuthUserResponse

logger = logging.getLogger(__name__)
security = HTTPBasic()
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)


def fingerprint_sensitive_value(value: str) -> str:
    if not value:
        raise ValueError("Value is required to build a fingerprint.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def hash_password(password: str) -> str:
    try:
        return password_hasher.hash(password)
    except HashingError as exc:
        logger.exception("Password hashing failed.")
        raise RuntimeError("Password hashing failed.") from exc


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        logger.info("Password verification failed due to mismatch.")
        return False
    except (InvalidHashError, VerificationError) as exc:
        logger.exception("Stored password hash verification failed.")
        raise RuntimeError("Stored password hash verification failed.") from exc


def generate_one_time_code(length: int) -> str:
    if length <= 0:
        raise ValueError("One-time code length must be positive.")
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))


def hash_one_time_code(code: str) -> str:
    if not code:
        raise ValueError("One-time code cannot be empty.")
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def build_one_time_code(length: int, ttl_minutes: int) -> tuple[str, str, datetime]:
    if ttl_minutes <= 0:
        raise ValueError("One-time code TTL must be positive.")

    plain_code = generate_one_time_code(length)
    code_hash = hash_one_time_code(plain_code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    return plain_code, code_hash, expires_at


def verify_one_time_code(code: str, stored_code_hash: str) -> bool:
    if not code:
        raise ValueError("One-time code cannot be empty.")
    if not stored_code_hash:
        raise ValueError("Stored one-time code hash cannot be empty.")
    candidate_hash = hash_one_time_code(code)
    return secrets.compare_digest(candidate_hash, stored_code_hash)


def is_code_expired(expires_at: datetime) -> bool:
    return expires_at <= datetime.now(timezone.utc)


def set_auth_cookie(response: Response, session_id: str) -> None:
    if not session_id:
        raise ValueError("Session ID is required to set auth cookie.")

    max_age_seconds = int(timedelta(hours=settings.auth_session_ttl_hours).total_seconds())
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=max_age_seconds,
        expires=max_age_seconds,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def build_auth_user_response(user: WebUserDB) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        is_active=user.is_active,
        name=user.name,
        company=user.company,
    )


async def create_auth_session_for_user(user_id: str) -> AuthSessionDB:
    if not user_id:
        raise ValueError("User ID is required to create auth session.")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.auth_session_ttl_hours)
    session = AuthSessionDB(
        session_id=secrets.token_urlsafe(32),
        user_id=user_id,
        expires_at=expires_at,
    )
    return await db.create_auth_session(session)


def get_session_id_from_request(request: Request) -> str | None:
    return request.cookies.get(settings.auth_cookie_name)


async def get_current_user(request: Request) -> WebUserDB:
    session_id = get_session_id_from_request(request)
    if session_id is None:
        logger.info("Auth session rejected because cookie is missing.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    session = await db.get_auth_session(session_id)
    if session is None:
        logger.info("Auth session rejected because session is invalid or expired.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    user = await db.get_web_user_by_id(session.user_id)
    if user is None:
        logger.error(
            "Auth session references unknown user. session_fingerprint=%s user_id=%s",
            fingerprint_sensitive_value(session_id),
            session.user_id,
        )
        await db.delete_auth_session(session_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


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
    correct_username = secrets.compare_digest(credentials.username, settings.moderator_username)
    correct_password = secrets.compare_digest(credentials.password, settings.moderator_password)

    if not (correct_username and correct_password):
        logger.warning("Failed moderator authentication attempt for user: %s", credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    logger.info("User '%s' authenticated successfully.", credentials.username)
    return credentials.username