from base64 import b64encode
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging

from fastapi.testclient import TestClient

from shared import db
from web.config import settings

INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."
NEUTRAL_VERIFICATION_MESSAGE = "If the account is eligible, a verification code has been sent."
NEUTRAL_PASSWORD_RESET_MESSAGE = "If the account is eligible, a password reset code has been sent."


def _register(
    client: TestClient,
    *,
    email: str = "  User@Example.com  ",
    password: str = "Password1",
    confirm_password: str = "Password1",
):
    return client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": confirm_password,
        },
    )


def _login(client: TestClient, *, email: str = "user@example.com", password: str = "Password1"):
    return client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


def _authorization_header(username: str, password: str) -> dict[str, str]:
    token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_register_me_logout_flow_enforces_cookie_contract(app_client: TestClient) -> None:
    response = _register(app_client)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"

    set_cookie_header = response.headers["set-cookie"].lower()
    assert f"{settings.auth_cookie_name}=" in set_cookie_header
    assert "httponly" in set_cookie_header
    assert "path=/" in set_cookie_header
    assert f"samesite={settings.auth_cookie_samesite}" in set_cookie_header
    assert "; secure" not in set_cookie_header

    me_response = app_client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user@example.com"

    logout_response = app_client.post("/auth/logout")
    assert logout_response.status_code == 200

    unauthenticated_response = app_client.get("/auth/me")
    assert unauthenticated_response.status_code == 401


def test_cors_preflight_allows_configured_origin_and_credentials(app_client: TestClient) -> None:
    response = app_client.options(
        "/auth/login",
        headers={
            "Origin": settings.front_base_url,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.front_base_url
    assert response.headers["access-control-allow-credentials"] == "true"


def test_auth_me_rejects_missing_invalid_and_expired_sessions(app_client: TestClient) -> None:
    missing_cookie_response = app_client.get("/auth/me")
    assert missing_cookie_response.status_code == 401

    app_client.cookies.set(settings.auth_cookie_name, "invalid-session")
    invalid_cookie_response = app_client.get("/auth/me")
    assert invalid_cookie_response.status_code == 401

    app_client.cookies.clear()
    register_response = _register(app_client)
    assert register_response.status_code == 200

    session_id = app_client.cookies.get(settings.auth_cookie_name)
    assert session_id is not None

    db._auth_sessions[session_id].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired_session_response = app_client.get("/auth/me")
    assert expired_session_response.status_code == 401
    assert session_id not in db._auth_sessions


def test_register_rejects_duplicate_invalid_email_and_weak_password(app_client: TestClient) -> None:
    first_response = _register(app_client)
    assert first_response.status_code == 200

    duplicate_response = _register(app_client, email="USER@example.com")
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "User with this email already exists."

    invalid_email_response = _register(app_client, email="not-an-email")
    assert invalid_email_response.status_code == 422

    weak_password_response = _register(app_client, email="weak@example.com", password="weakpass", confirm_password="weakpass")
    assert weak_password_response.status_code == 400
    assert weak_password_response.json()["detail"] == "Password must contain at least one digit."


def test_login_uses_generic_failures_for_missing_user_and_wrong_password(app_client: TestClient) -> None:
    missing_user_response = _login(app_client)
    assert missing_user_response.status_code == 401
    assert missing_user_response.json()["detail"] == INVALID_CREDENTIALS_MESSAGE

    register_response = _register(app_client)
    assert register_response.status_code == 200

    wrong_password_response = _login(app_client, password="WrongPassword1")
    assert wrong_password_response.status_code == 401
    assert wrong_password_response.json()["detail"] == INVALID_CREDENTIALS_MESSAGE


def test_verification_flow_is_neutral_and_never_logs_plain_code(
    app_client: TestClient,
    captured_email_codes: dict[str, dict[str, str]],
    caplog,
) -> None:
    missing_user_response = app_client.post("/auth/send-verification-code", json={"email": "missing@example.com"})
    assert missing_user_response.status_code == 200
    assert missing_user_response.json() == {"success": True, "message": NEUTRAL_VERIFICATION_MESSAGE}

    register_response = _register(app_client)
    assert register_response.status_code == 200

    with caplog.at_level(logging.INFO):
        send_code_response = app_client.post("/auth/send-verification-code", json={"email": "user@example.com"})

    assert send_code_response.status_code == 200
    assert send_code_response.json() == {"success": True, "message": NEUTRAL_VERIFICATION_MESSAGE}

    verification_code = captured_email_codes["verification"]["user@example.com"]
    assert verification_code.isdigit()
    assert verification_code not in send_code_response.text
    assert verification_code not in caplog.text

    invalid_code_response = app_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": "999999",
        },
    )
    assert invalid_code_response.status_code == 400
    assert invalid_code_response.json()["detail"] == "Invalid or expired verification code."

    verify_response = app_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": verification_code,
        },
    )
    assert verify_response.status_code == 200

    me_response = app_client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email_verified"] is True


def test_verify_email_rejects_expired_and_over_limit_codes(
    app_client: TestClient,
    captured_email_codes: dict[str, dict[str, str]],
) -> None:
    register_response = _register(app_client)
    assert register_response.status_code == 200

    send_code_response = app_client.post("/auth/send-verification-code", json={"email": "user@example.com"})
    assert send_code_response.status_code == 200

    expired_code = captured_email_codes["verification"]["user@example.com"]
    user = db._web_users["user@example.com"]
    user.email_verification_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired_response = app_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": expired_code,
        },
    )
    assert expired_response.status_code == 400
    assert expired_response.json()["detail"] == "Invalid or expired verification code."

    resend_response = app_client.post("/auth/send-verification-code", json={"email": "user@example.com"})
    assert resend_response.status_code == 200

    for _ in range(settings.auth_max_code_attempts - 1):
        invalid_attempt_response = app_client.post(
            "/auth/verify-email",
            json={
                "email": "user@example.com",
                "code": "999999",
            },
        )
        assert invalid_attempt_response.status_code == 400

    over_limit_response = app_client.post(
        "/auth/verify-email",
        json={
            "email": "user@example.com",
            "code": "999999",
        },
    )
    assert over_limit_response.status_code == 429
    assert over_limit_response.json()["detail"] == "Verification attempt limit exceeded. Request a new code."


def test_password_reset_is_neutral_invalidates_all_sessions_and_allows_new_login(
    client_factory: Callable[[], TestClient],
    captured_email_codes: dict[str, dict[str, str]],
    caplog,
) -> None:
    primary_client = client_factory()
    secondary_client = client_factory()

    neutral_response = primary_client.post("/auth/request-password-reset", json={"email": "missing@example.com"})
    assert neutral_response.status_code == 200
    assert neutral_response.json() == {"success": True, "message": NEUTRAL_PASSWORD_RESET_MESSAGE}

    register_response = _register(primary_client)
    assert register_response.status_code == 200

    secondary_login_response = _login(secondary_client)
    assert secondary_login_response.status_code == 200

    with caplog.at_level(logging.INFO):
        request_reset_response = primary_client.post("/auth/request-password-reset", json={"email": "user@example.com"})

    assert request_reset_response.status_code == 200
    assert request_reset_response.json() == {"success": True, "message": NEUTRAL_PASSWORD_RESET_MESSAGE}

    reset_code = captured_email_codes["reset"]["user@example.com"]
    assert reset_code not in request_reset_response.text
    assert reset_code not in caplog.text

    reset_response = primary_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": reset_code,
            "new_password": "NewPassword1",
            "confirm_password": "NewPassword1",
        },
    )
    assert reset_response.status_code == 200

    assert primary_client.get("/auth/me").status_code == 401
    assert secondary_client.get("/auth/me").status_code == 401

    old_password_login_response = _login(primary_client)
    assert old_password_login_response.status_code == 401
    assert old_password_login_response.json()["detail"] == INVALID_CREDENTIALS_MESSAGE

    new_password_login_response = _login(primary_client, password="NewPassword1")
    assert new_password_login_response.status_code == 200
    assert new_password_login_response.json()["email"] == "user@example.com"


def test_reset_password_rejects_invalid_expired_and_over_limit_codes(
    app_client: TestClient,
    captured_email_codes: dict[str, dict[str, str]],
) -> None:
    register_response = _register(app_client)
    assert register_response.status_code == 200

    request_reset_response = app_client.post("/auth/request-password-reset", json={"email": "user@example.com"})
    assert request_reset_response.status_code == 200

    expired_code = captured_email_codes["reset"]["user@example.com"]
    user = db._web_users["user@example.com"]
    user.password_reset_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired_response = app_client.post(
        "/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": expired_code,
            "new_password": "NextPassword1",
            "confirm_password": "NextPassword1",
        },
    )
    assert expired_response.status_code == 400
    assert expired_response.json()["detail"] == "Password reset code has expired."

    resend_response = app_client.post("/auth/request-password-reset", json={"email": "user@example.com"})
    assert resend_response.status_code == 200

    for _ in range(settings.auth_max_code_attempts - 1):
        invalid_attempt_response = app_client.post(
            "/auth/reset-password",
            json={
                "email": "user@example.com",
                "code": "999999",
                "new_password": "NextPassword1",
                "confirm_password": "NextPassword1",
            },
        )
        assert invalid_attempt_response.status_code == 400

    over_limit_response = app_client.post(
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


def test_moderator_basic_auth_still_works(app_client: TestClient) -> None:
    unauthorized_response = app_client.get("/docs")
    assert unauthorized_response.status_code == 401

    authorized_response = app_client.get(
        "/docs",
        headers=_authorization_header("admin", "password"),
    )
    assert authorized_response.status_code == 200
    assert "text/html" in authorized_response.headers["content-type"]
