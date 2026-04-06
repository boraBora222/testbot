from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request, Response

from shared.models import WebUserDB
from web.auth import (
    build_auth_user_response,
    build_one_time_code,
    clear_auth_cookie,
    fingerprint_sensitive_value,
    generate_one_time_code,
    get_session_id_from_request,
    hash_one_time_code,
    hash_password,
    is_code_expired,
    set_auth_cookie,
    verify_one_time_code,
    verify_password,
)
from web.config import settings


def _build_request_with_cookie(session_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/me",
            "query_string": b"",
            "headers": [(b"cookie", f"{settings.auth_cookie_name}={session_id}".encode("ascii"))],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "root_path": "",
            "http_version": "1.1",
        }
    )


def test_fingerprint_sensitive_value_returns_stable_short_hash() -> None:
    value = "user@example.com"

    first_fingerprint = fingerprint_sensitive_value(value)
    second_fingerprint = fingerprint_sensitive_value(value)

    assert first_fingerprint == second_fingerprint
    assert len(first_fingerprint) == 12
    assert first_fingerprint != fingerprint_sensitive_value("other@example.com")


def test_fingerprint_sensitive_value_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="Value is required"):
        fingerprint_sensitive_value("")


def test_password_hashing_and_verification_cover_success_mismatch_and_invalid_hash() -> None:
    password_hash = hash_password("Password1")

    assert password_hash != "Password1"
    assert verify_password("Password1", password_hash) is True
    assert verify_password("WrongPassword1", password_hash) is False

    with pytest.raises(RuntimeError, match="Stored password hash verification failed"):
        verify_password("Password1", "not-a-valid-argon-hash")


def test_one_time_code_helpers_build_hash_and_verify() -> None:
    generated_code = generate_one_time_code(6)
    generated_hash = hash_one_time_code(generated_code)
    plain_code, code_hash, expires_at = build_one_time_code(6, 10)

    assert generated_code.isdigit()
    assert len(generated_code) == 6
    assert generated_hash == hash_one_time_code(generated_code)
    assert plain_code.isdigit()
    assert len(plain_code) == 6
    assert verify_one_time_code(plain_code, code_hash) is True
    assert verify_one_time_code("000000", code_hash) is False
    assert expires_at > datetime.now(timezone.utc)


def test_one_time_code_helpers_reject_invalid_input() -> None:
    with pytest.raises(ValueError, match="length must be positive"):
        generate_one_time_code(0)

    with pytest.raises(ValueError, match="cannot be empty"):
        hash_one_time_code("")

    with pytest.raises(ValueError, match="TTL must be positive"):
        build_one_time_code(6, 0)

    with pytest.raises(ValueError, match="One-time code cannot be empty"):
        verify_one_time_code("", "hash")

    with pytest.raises(ValueError, match="Stored one-time code hash cannot be empty"):
        verify_one_time_code("123456", "")


def test_is_code_expired_distinguishes_future_and_past_timestamps() -> None:
    future_expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    past_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert is_code_expired(future_expires_at) is False
    assert is_code_expired(past_expires_at) is True


def test_cookie_helpers_set_clear_and_read_auth_session_cookie() -> None:
    response = Response()

    set_auth_cookie(response, "session-123")
    set_cookie_header = response.headers["set-cookie"].lower()

    assert f"{settings.auth_cookie_name}=session-123" in set_cookie_header
    assert "httponly" in set_cookie_header
    assert f"samesite={settings.auth_cookie_samesite}" in set_cookie_header
    assert "path=/" in set_cookie_header

    request = _build_request_with_cookie("session-123")
    assert get_session_id_from_request(request) == "session-123"

    clear_auth_cookie(response)
    cleared_cookie_header = response.headers.getlist("set-cookie")[-1].lower()
    assert settings.auth_cookie_name in cleared_cookie_header
    assert "max-age=0" in cleared_cookie_header


def test_set_auth_cookie_requires_session_id() -> None:
    with pytest.raises(ValueError, match="Session ID is required"):
        set_auth_cookie(Response(), "")


def test_build_auth_user_response_maps_public_fields() -> None:
    user = WebUserDB(
        id="user_123",
        email="user@example.com",
        password_hash="hash",
        email_verified=True,
        is_active=True,
        name="Alice",
        company="Acme",
    )

    response = build_auth_user_response(user)

    assert response.id == "user_123"
    assert response.email == "user@example.com"
    assert response.email_verified is True
    assert response.is_active is True
    assert response.name == "Alice"
    assert response.company == "Acme"
