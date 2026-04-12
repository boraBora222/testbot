from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from shared import db
from web.config import settings
import web.routers.auth as auth_router

pytestmark = pytest.mark.anyio


async def _register(
    client: httpx.AsyncClient,
    *,
    email: str = "User@Example.com",
    password: str = "Password1",
    confirm_password: str = "Password1",
    first_name: str = "Test",
    last_name: str = "User",
    company: str = "Example LLC",
) -> httpx.Response:
    return await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": confirm_password,
            "first_name": first_name,
            "last_name": last_name,
            "company": company,
        },
    )


async def _login(
    client: httpx.AsyncClient,
    *,
    email: str = "user@example.com",
    password: str = "Password1",
) -> httpx.Response:
    return await client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


async def _request_verification_code(client: httpx.AsyncClient, email: str = "user@example.com") -> httpx.Response:
    return await client.post("/auth/send-verification-code", json={"email": email})


async def _request_password_reset(client: httpx.AsyncClient, email: str = "user@example.com") -> httpx.Response:
    return await client.post("/auth/request-password-reset", json={"email": email})


async def test_register_rejects_duplicate_password_mismatch_and_weak_password(
    auth_async_client: httpx.AsyncClient,
) -> None:
    register_response = await _register(auth_async_client)
    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["email"] == "user@example.com"
    assert register_payload["first_name"] == "Test"
    assert register_payload["last_name"] == "User"
    assert register_payload["company"] == "Example LLC"
    assert register_payload["name"] == "Test User"
    stored_user = db._web_users["user@example.com"]
    assert stored_user.linked_exchange_user_id is not None
    assert stored_user.linked_exchange_user_id < 0

    shadow_exchange_user = await db.get_exchange_user(stored_user.linked_exchange_user_id)
    assert shadow_exchange_user is not None
    assert shadow_exchange_user["telegram_user_id"] == stored_user.linked_exchange_user_id
    assert shadow_exchange_user["first_name"] == "Test"
    assert shadow_exchange_user["last_name"] == "User"
    assert shadow_exchange_user["notification_preferences"]["telegram_enabled"] is False
    assert shadow_exchange_user["notification_preferences"]["email_enabled"] is True
    quota_payload = await db.get_limit_quota(stored_user.linked_exchange_user_id)
    assert quota_payload is not None
    assert quota_payload["user_id"] == stored_user.linked_exchange_user_id
    assert quota_payload["verification_level"] == settings.web_registration_default_verification_level
    assert quota_payload["daily_limit"] == settings.web_registration_default_daily_limit
    assert quota_payload["daily_used"] == 0
    assert quota_payload["monthly_limit"] == settings.web_registration_default_monthly_limit
    assert quota_payload["monthly_used"] == 0

    duplicate_response = await _register(auth_async_client, email="USER@example.com")
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "User with this email already exists."

    mismatch_response = await _register(
        auth_async_client,
        email="mismatch@example.com",
        confirm_password="OtherPassword1",
    )
    assert mismatch_response.status_code == 400
    assert mismatch_response.json()["detail"] == "Password and confirm_password must match."

    weak_password_response = await _register(
        auth_async_client,
        email="weak@example.com",
        password="password",
        confirm_password="password",
    )
    assert weak_password_response.status_code == 400
    assert weak_password_response.json()["detail"] == "Password must contain at least one digit."


async def test_login_me_logout_and_expired_session_flow(auth_async_client: httpx.AsyncClient) -> None:
    missing_me_response = await auth_async_client.get("/auth/me")
    assert missing_me_response.status_code == 401

    register_response = await _register(auth_async_client)
    assert register_response.status_code == 200

    session_id = auth_async_client.cookies.get(settings.auth_cookie_name)
    assert session_id is not None
    assert session_id in db._auth_sessions

    me_response = await auth_async_client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user@example.com"

    logout_response = await auth_async_client.post("/auth/logout")
    assert logout_response.status_code == 200
    assert session_id not in db._auth_sessions
    assert "max-age=0" in logout_response.headers["set-cookie"].lower()

    unauthorized_me_response = await auth_async_client.get("/auth/me")
    assert unauthorized_me_response.status_code == 401

    missing_user_login_response = await _login(auth_async_client, email="missing@example.com")
    assert missing_user_login_response.status_code == 401
    assert missing_user_login_response.json()["detail"] == auth_router.INVALID_CREDENTIALS_MESSAGE

    await _register(auth_async_client, email="another@example.com", password="Password2", confirm_password="Password2")
    wrong_password_login_response = await _login(
        auth_async_client,
        email="another@example.com",
        password="WrongPassword2",
    )
    assert wrong_password_login_response.status_code == 401
    assert wrong_password_login_response.json()["detail"] == auth_router.INVALID_CREDENTIALS_MESSAGE

    success_login_response = await _login(
        auth_async_client,
        email="another@example.com",
        password="Password2",
    )
    assert success_login_response.status_code == 200

    new_session_id = auth_async_client.cookies.get(settings.auth_cookie_name)
    assert new_session_id is not None
    db._auth_sessions[new_session_id].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired_me_response = await auth_async_client.get("/auth/me")
    assert expired_me_response.status_code == 401
    assert new_session_id not in db._auth_sessions


async def test_send_verification_code_is_neutral_for_missing_and_verified_users(
    auth_async_client: httpx.AsyncClient,
    captured_email_codes: dict[str, dict[str, str]],
) -> None:
    missing_user_response = await _request_verification_code(auth_async_client, "missing@example.com")
    assert missing_user_response.status_code == 200
    assert missing_user_response.json() == {
        "success": True,
        "message": auth_router.NEUTRAL_VERIFICATION_MESSAGE,
    }

    await _register(auth_async_client)
    user = db._web_users["user@example.com"]
    user.email_verified = True

    verified_user_response = await _request_verification_code(auth_async_client, "user@example.com")
    assert verified_user_response.status_code == 200
    assert verified_user_response.json() == {
        "success": True,
        "message": auth_router.NEUTRAL_VERIFICATION_MESSAGE,
    }
    assert captured_email_codes["verification"] == {}


async def test_verify_email_flow_supports_success_invalid_code_and_invalid_format(
    auth_async_client: httpx.AsyncClient,
    captured_email_codes: dict[str, dict[str, str]],
) -> None:
    await _register(auth_async_client)

    send_code_response = await _request_verification_code(auth_async_client)
    assert send_code_response.status_code == 200

    invalid_format_response = await auth_async_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": "12ab",
        },
    )
    assert invalid_format_response.status_code == 400
    assert invalid_format_response.json()["detail"] == (
        "Verification code must contain only digits and match the configured length."
    )

    invalid_code_response = await auth_async_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": "999999",
        },
    )
    assert invalid_code_response.status_code == 400
    assert invalid_code_response.json()["detail"] == auth_router.INVALID_VERIFICATION_CODE_MESSAGE

    verification_code = captured_email_codes["verification"]["user@example.com"]
    verify_response = await auth_async_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": verification_code,
        },
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["message"] == "Email verified successfully."
    assert db._web_users["user@example.com"].email_verified is True


async def test_verify_email_rejects_expired_code_and_blocks_after_max_attempts(
    auth_async_client: httpx.AsyncClient,
    captured_email_codes: dict[str, dict[str, str]],
) -> None:
    await _register(auth_async_client)
    await _request_verification_code(auth_async_client)

    verification_code = captured_email_codes["verification"]["user@example.com"]
    db._web_users["user@example.com"].email_verification_code_expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    expired_response = await auth_async_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": verification_code,
        },
    )
    assert expired_response.status_code == 400
    assert expired_response.json()["detail"] == auth_router.INVALID_VERIFICATION_CODE_MESSAGE

    await _request_verification_code(auth_async_client)
    for _ in range(settings.auth_max_code_attempts - 1):
        invalid_attempt_response = await auth_async_client.post(
            "/auth/verify-email",
            json={
                "email": "user@example.com",
                "code": "999999",
            },
        )
        assert invalid_attempt_response.status_code == 400

    over_limit_response = await auth_async_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": "999999",
        },
    )
    assert over_limit_response.status_code == 429
    assert over_limit_response.json()["detail"] == "Verification attempt limit exceeded. Request a new code."


async def test_send_verification_code_clears_stored_code_when_email_delivery_fails(
    auth_async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register(auth_async_client)

    async def failing_send_verification_code(email: str, code: str) -> None:
        raise RuntimeError(f"SMTP delivery failed for {email}:{code}")

    monkeypatch.setattr(auth_router, "send_verification_code_email", failing_send_verification_code)

    response = await _request_verification_code(auth_async_client)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to send verification code."
    user = db._web_users["user@example.com"]
    assert user.email_verification_code_hash is None
    assert user.email_verification_code_expires_at is None
    assert user.email_verification_attempts == 0


async def test_password_reset_request_is_neutral_and_validates_payload_rules(
    auth_async_client: httpx.AsyncClient,
) -> None:
    missing_user_response = await _request_password_reset(auth_async_client, "missing@example.com")
    assert missing_user_response.status_code == 200
    assert missing_user_response.json() == {
        "success": True,
        "message": auth_router.NEUTRAL_PASSWORD_RESET_MESSAGE,
    }

    await _register(auth_async_client)
    await _request_password_reset(auth_async_client)

    invalid_format_response = await auth_async_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": "12ab",
            "new_password": "NextPassword1",
            "confirm_password": "NextPassword1",
        },
    )
    assert invalid_format_response.status_code == 400
    assert invalid_format_response.json()["detail"] == (
        "Password reset code must contain only digits and match the configured length."
    )

    mismatch_response = await auth_async_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "NextPassword1",
            "confirm_password": "OtherPassword1",
        },
    )
    assert mismatch_response.status_code == 400
    assert mismatch_response.json()["detail"] == "Password and confirm_password must match."

    weak_password_response = await auth_async_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "password",
            "confirm_password": "password",
        },
    )
    assert weak_password_response.status_code == 400
    assert weak_password_response.json()["detail"] == "Password must contain at least one digit."


async def test_password_reset_flow_invalidates_all_active_sessions(
    auth_app,
    captured_email_codes: dict[str, dict[str, str]],
) -> None:
    transport = httpx.ASGITransport(app=auth_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as primary_client:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as secondary_client:
            register_response = await _register(primary_client)
            assert register_response.status_code == 200

            secondary_login_response = await _login(secondary_client)
            assert secondary_login_response.status_code == 200

            request_reset_response = await _request_password_reset(primary_client)
            assert request_reset_response.status_code == 200

            reset_code = captured_email_codes["reset"]["user@example.com"]
            reset_response = await primary_client.post(
                "/auth/reset-password",
                json={
                    "email": "user@example.com",
                    "code": reset_code,
                    "new_password": "NewPassword1",
                    "confirm_password": "NewPassword1",
                },
            )
            assert reset_response.status_code == 200

            assert (await primary_client.get("/auth/me")).status_code == 401
            assert (await secondary_client.get("/auth/me")).status_code == 401

            old_password_login_response = await _login(primary_client, password="Password1")
            assert old_password_login_response.status_code == 401

            new_password_login_response = await _login(primary_client, password="NewPassword1")
            assert new_password_login_response.status_code == 200


async def test_reset_password_rejects_expired_invalid_and_over_limit_codes(
    auth_async_client: httpx.AsyncClient,
    captured_email_codes: dict[str, dict[str, str]],
) -> None:
    await _register(auth_async_client)
    await _request_password_reset(auth_async_client)

    invalid_code_response = await auth_async_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": "999999",
            "new_password": "NextPassword1",
            "confirm_password": "NextPassword1",
        },
    )
    assert invalid_code_response.status_code == 400
    assert invalid_code_response.json()["detail"] == auth_router.INVALID_PASSWORD_RESET_CODE_MESSAGE

    await _request_password_reset(auth_async_client)
    reset_code = captured_email_codes["reset"]["user@example.com"]
    db._web_users["user@example.com"].password_reset_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired_response = await auth_async_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": reset_code,
            "new_password": "NextPassword1",
            "confirm_password": "NextPassword1",
        },
    )
    assert expired_response.status_code == 400
    assert expired_response.json()["detail"] == auth_router.EXPIRED_PASSWORD_RESET_CODE_MESSAGE

    await _request_password_reset(auth_async_client)
    for _ in range(settings.auth_max_code_attempts - 1):
        invalid_attempt_response = await auth_async_client.post(
            "/auth/reset-password",
            json={
                "email": "user@example.com",
                "code": "999999",
                "new_password": "NextPassword1",
                "confirm_password": "NextPassword1",
            },
        )
        assert invalid_attempt_response.status_code == 400

    over_limit_response = await auth_async_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": "999999",
            "new_password": "NextPassword1",
            "confirm_password": "NextPassword1",
        },
    )
    assert over_limit_response.status_code == 429
    assert over_limit_response.json()["detail"] == "Password reset attempt limit exceeded. Request a new code."


async def test_request_password_reset_clears_stored_code_when_email_delivery_fails(
    auth_async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register(auth_async_client)

    async def failing_send_password_reset_code(email: str, code: str) -> None:
        raise RuntimeError(f"SMTP delivery failed for {email}:{code}")

    monkeypatch.setattr(auth_router, "send_password_reset_code_email", failing_send_password_reset_code)

    response = await _request_password_reset(auth_async_client)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to send password reset code."
    user = db._web_users["user@example.com"]
    assert user.password_reset_code_hash is None
    assert user.password_reset_code_expires_at is None
    assert user.password_reset_attempts == 0
