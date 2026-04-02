import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from shared import db
from shared.models import WebUserDB
from web.auth import (
    build_auth_user_response,
    build_one_time_code,
    clear_auth_cookie,
    create_auth_session_for_user,
    fingerprint_sensitive_value,
    get_current_user,
    get_session_id_from_request,
    hash_password,
    is_code_expired,
    set_auth_cookie,
    verify_one_time_code,
    verify_password,
)
from web.config import settings
from web.models import (
    AuthUserResponse,
    LoginRequest,
    RequestPasswordResetRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SendVerificationCodeRequest,
    SimpleSuccessResponse,
    VerifyEmailRequest,
)
from web.services.email_service import send_verification_code as send_verification_code_email
from web.services.email_service import send_password_reset_code as send_password_reset_code_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."
NEUTRAL_VERIFICATION_MESSAGE = "If the account is eligible, a verification code has been sent."
INVALID_VERIFICATION_CODE_MESSAGE = "Invalid or expired verification code."
NEUTRAL_PASSWORD_RESET_MESSAGE = "If the account is eligible, a password reset code has been sent."
INVALID_PASSWORD_RESET_CODE_MESSAGE = "Invalid password reset code."
EXPIRED_PASSWORD_RESET_CODE_MESSAGE = "Password reset code has expired."


def _validate_password_confirmation(password: str, confirm_password: str) -> None:
    if password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password and confirm_password must match.",
        )


def _validate_password_policy(password: str) -> None:
    if len(password) < settings.auth_password_min_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {settings.auth_password_min_length} characters long.",
        )
    if not any(character.isalpha() for character in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one letter.",
        )
    if not any(character.isdigit() for character in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one digit.",
        )


def _validate_one_time_code_format(code: str, expected_length: int, code_kind: str) -> None:
    if len(code) != expected_length or not code.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{code_kind} code must contain only digits and match the configured length.",
        )


@router.post("/register", response_model=AuthUserResponse)
async def register(payload: RegisterRequest, response: Response) -> AuthUserResponse:
    _validate_password_confirmation(payload.password, payload.confirm_password)
    _validate_password_policy(payload.password)

    existing_user = await db.get_web_user_by_email(payload.email)
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this email already exists.")

    user = WebUserDB(
        id=f"user_{uuid.uuid4().hex}",
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    await db.create_web_user(user)

    session = await create_auth_session_for_user(user.id)
    set_auth_cookie(response, session.session_id)
    logger.info("Website user registered successfully. user_id=%s", user.id)
    return build_auth_user_response(user)


@router.post("/login", response_model=AuthUserResponse)
async def login(payload: LoginRequest, response: Response) -> AuthUserResponse:
    user = await db.get_web_user_by_email(payload.email)
    if user is None:
        logger.info(
            "Website login failed because user was not found. email_fingerprint=%s",
            fingerprint_sensitive_value(payload.email),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_MESSAGE)

    if not verify_password(payload.password, user.password_hash):
        logger.info("Website login failed because password verification failed. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_MESSAGE)

    await db.update_web_user_last_login(user.id)
    refreshed_user = await db.get_web_user_by_id(user.id)
    if refreshed_user is None:
        logger.error("Website login failed because user disappeared after update. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to complete login.")

    session = await create_auth_session_for_user(refreshed_user.id)
    set_auth_cookie(response, session.session_id)
    logger.info("Website user logged in successfully. user_id=%s", refreshed_user.id)
    return build_auth_user_response(refreshed_user)


@router.post("/logout", response_model=SimpleSuccessResponse)
async def logout(request: Request, response: Response) -> SimpleSuccessResponse:
    session_id = get_session_id_from_request(request)
    if session_id is not None:
        await db.delete_auth_session(session_id)
        logger.info(
            "Website auth session deleted during logout. session_fingerprint=%s",
            fingerprint_sensitive_value(session_id),
        )
    clear_auth_cookie(response)
    return SimpleSuccessResponse(message="Logged out successfully.")


@router.get("/me", response_model=AuthUserResponse)
async def me(current_user: WebUserDB = Depends(get_current_user)) -> AuthUserResponse:
    return build_auth_user_response(current_user)


@router.post("/send-verification-code", response_model=SimpleSuccessResponse)
async def send_verification_code(payload: SendVerificationCodeRequest) -> SimpleSuccessResponse:
    user = await db.get_web_user_by_email(payload.email)
    if user is None:
        logger.info(
            "Verification code request completed with neutral response for missing user. email_fingerprint=%s",
            fingerprint_sensitive_value(payload.email),
        )
        return SimpleSuccessResponse(message=NEUTRAL_VERIFICATION_MESSAGE)
    if user.email_verified:
        logger.info("Verification code request completed with neutral response for verified user. user_id=%s", user.id)
        return SimpleSuccessResponse(message=NEUTRAL_VERIFICATION_MESSAGE)

    plain_code, code_hash, expires_at = build_one_time_code(
        settings.auth_verification_code_length,
        settings.auth_verification_code_ttl_minutes,
    )
    await db.set_email_verification_code(user.id, code_hash, expires_at)

    try:
        await send_verification_code_email(user.email, plain_code)
    except RuntimeError as exc:
        logger.exception("Verification code delivery failed. user_id=%s", user.id)
        await db.clear_email_verification_code(user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification code.",
        ) from exc

    logger.info("Verification code issued successfully. user_id=%s", user.id)
    return SimpleSuccessResponse(message=NEUTRAL_VERIFICATION_MESSAGE)


@router.post("/verify-email", response_model=SimpleSuccessResponse)
async def verify_email(payload: VerifyEmailRequest) -> SimpleSuccessResponse:
    _validate_one_time_code_format(payload.code, settings.auth_verification_code_length, "Verification")

    user = await db.get_web_user_by_email(payload.email)
    if user is None or user.email_verified:
        logger.info(
            "Email verification rejected with generic response. email_fingerprint=%s",
            fingerprint_sensitive_value(payload.email),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_VERIFICATION_CODE_MESSAGE)

    if user.email_verification_attempts >= settings.auth_max_code_attempts:
        logger.warning("Email verification blocked because attempt limit was reached. user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Verification attempt limit exceeded. Request a new code.",
        )

    if user.email_verification_code_hash is None or user.email_verification_code_expires_at is None:
        logger.info("Email verification rejected because no active code is available. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_VERIFICATION_CODE_MESSAGE)

    if is_code_expired(user.email_verification_code_expires_at):
        await db.increment_email_verification_attempts(user.id)
        refreshed_user = await db.get_web_user_by_id(user.id)
        if refreshed_user is None:
            logger.error("Expired verification attempt update failed because user disappeared. user_id=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process verification request.",
            )
        if refreshed_user.email_verification_attempts >= settings.auth_max_code_attempts:
            logger.warning("Expired verification code consumed the final allowed attempt. user_id=%s", refreshed_user.id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Verification attempt limit exceeded. Request a new code.",
            )
        logger.info("Email verification rejected because code expired. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_VERIFICATION_CODE_MESSAGE)

    if not verify_one_time_code(payload.code, user.email_verification_code_hash):
        await db.increment_email_verification_attempts(user.id)
        refreshed_user = await db.get_web_user_by_id(user.id)
        if refreshed_user is None:
            logger.error("Verification attempt update failed because user disappeared. user_id=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process verification request.",
            )
        if refreshed_user.email_verification_attempts >= settings.auth_max_code_attempts:
            logger.warning("Email verification blocked after reaching max attempts. user_id=%s", refreshed_user.id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Verification attempt limit exceeded. Request a new code.",
            )
        logger.info("Email verification rejected because code hash comparison failed. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_VERIFICATION_CODE_MESSAGE)

    await db.mark_web_user_email_verified(user.id)
    logger.info("Email verified successfully. user_id=%s", user.id)
    return SimpleSuccessResponse(message="Email verified successfully.")


@router.post("/request-password-reset", response_model=SimpleSuccessResponse)
async def request_password_reset(payload: RequestPasswordResetRequest) -> SimpleSuccessResponse:
    user = await db.get_web_user_by_email(payload.email)
    if user is None:
        logger.info(
            "Password reset request completed with neutral response for missing user. email_fingerprint=%s",
            fingerprint_sensitive_value(payload.email),
        )
        return SimpleSuccessResponse(message=NEUTRAL_PASSWORD_RESET_MESSAGE)

    plain_code, code_hash, expires_at = build_one_time_code(
        settings.auth_reset_code_length,
        settings.auth_reset_code_ttl_minutes,
    )
    await db.set_password_reset_code(user.id, code_hash, expires_at)

    try:
        await send_password_reset_code_email(user.email, plain_code)
    except RuntimeError as exc:
        logger.exception("Password reset code delivery failed. user_id=%s", user.id)
        await db.clear_password_reset_code(user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send password reset code.",
        ) from exc

    logger.info("Password reset code issued successfully. user_id=%s", user.id)
    return SimpleSuccessResponse(message=NEUTRAL_PASSWORD_RESET_MESSAGE)


@router.post("/reset-password", response_model=SimpleSuccessResponse)
async def reset_password(payload: ResetPasswordRequest) -> SimpleSuccessResponse:
    _validate_password_confirmation(payload.new_password, payload.confirm_password)
    _validate_password_policy(payload.new_password)
    _validate_one_time_code_format(payload.code, settings.auth_reset_code_length, "Password reset")

    user = await db.get_web_user_by_email(payload.email)
    if user is None:
        logger.info(
            "Password reset rejected because user was not found. email_fingerprint=%s",
            fingerprint_sensitive_value(payload.email),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_PASSWORD_RESET_CODE_MESSAGE)

    if user.password_reset_attempts >= settings.auth_max_code_attempts:
        logger.warning("Password reset blocked because attempt limit was reached. user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Password reset attempt limit exceeded. Request a new code.",
        )

    if user.password_reset_code_hash is None or user.password_reset_code_expires_at is None:
        logger.info("Password reset rejected because no active code is available. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_PASSWORD_RESET_CODE_MESSAGE)

    if is_code_expired(user.password_reset_code_expires_at):
        await db.increment_password_reset_attempts(user.id)
        refreshed_user = await db.get_web_user_by_id(user.id)
        if refreshed_user is None:
            logger.error("Expired password reset attempt update failed because user disappeared. user_id=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process password reset request.",
            )
        if refreshed_user.password_reset_attempts >= settings.auth_max_code_attempts:
            logger.warning("Expired password reset code consumed the final allowed attempt. user_id=%s", refreshed_user.id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Password reset attempt limit exceeded. Request a new code.",
            )
        logger.info("Password reset rejected because code expired. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EXPIRED_PASSWORD_RESET_CODE_MESSAGE)

    if not verify_one_time_code(payload.code, user.password_reset_code_hash):
        await db.increment_password_reset_attempts(user.id)
        refreshed_user = await db.get_web_user_by_id(user.id)
        if refreshed_user is None:
            logger.error("Password reset attempt update failed because user disappeared. user_id=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process password reset request.",
            )
        if refreshed_user.password_reset_attempts >= settings.auth_max_code_attempts:
            logger.warning("Password reset blocked after reaching max attempts. user_id=%s", refreshed_user.id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Password reset attempt limit exceeded. Request a new code.",
            )
        logger.info("Password reset rejected because code hash comparison failed. user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_PASSWORD_RESET_CODE_MESSAGE)

    new_password_hash = hash_password(payload.new_password)
    await db.update_web_user_password_hash(user.id, new_password_hash)
    await db.clear_password_reset_code(user.id)
    await db.delete_auth_sessions_for_user(user.id)

    logger.info("Password reset completed successfully. user_id=%s", user.id)
    return SimpleSuccessResponse(message="Password updated successfully.")
