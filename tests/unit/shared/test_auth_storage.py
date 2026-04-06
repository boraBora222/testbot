from datetime import datetime, timedelta, timezone

import pytest

from shared import db
from shared.models import AuthSessionDB, WebUserDB

pytestmark = pytest.mark.anyio


def _build_user(*, email: str = "User@Example.com", user_id: str = "user_123") -> WebUserDB:
    return WebUserDB(
        id=user_id,
        email=email,
        password_hash="password-hash",
    )


async def test_web_user_storage_supports_case_insensitive_email_lookup() -> None:
    user = _build_user()

    await db.create_web_user(user)

    assert await db.get_web_user_by_email("user@example.com") == user
    assert await db.get_web_user_by_email("USER@EXAMPLE.COM") == user
    assert await db.get_web_user_by_id("user_123") == user


async def test_auth_sessions_can_be_created_loaded_deleted_and_expired() -> None:
    user = _build_user()
    await db.create_web_user(user)

    active_session = AuthSessionDB(
        session_id="session-active",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    expired_session = AuthSessionDB(
        session_id="session-expired",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    await db.create_auth_session(active_session)
    await db.create_auth_session(expired_session)

    assert await db.get_auth_session("session-active") == active_session
    assert await db.get_auth_session("session-expired") is None
    assert "session-expired" not in db._auth_sessions

    await db.delete_auth_session("session-active")
    assert await db.get_auth_session("session-active") is None


async def test_delete_auth_sessions_for_user_removes_only_target_user_sessions() -> None:
    first_user = _build_user(user_id="user_1", email="first@example.com")
    second_user = _build_user(user_id="user_2", email="second@example.com")
    await db.create_web_user(first_user)
    await db.create_web_user(second_user)

    await db.create_auth_session(
        AuthSessionDB(
            session_id="session-1",
            user_id=first_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )
    await db.create_auth_session(
        AuthSessionDB(
            session_id="session-2",
            user_id=first_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )
    await db.create_auth_session(
        AuthSessionDB(
            session_id="session-3",
            user_id=second_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )

    await db.delete_auth_sessions_for_user(first_user.id)

    assert "session-1" not in db._auth_sessions
    assert "session-2" not in db._auth_sessions
    assert "session-3" in db._auth_sessions


async def test_email_verification_code_lifecycle_updates_user_state() -> None:
    user = _build_user(email="verify@example.com")
    await db.create_web_user(user)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await db.set_email_verification_code(user.id, "verification-hash", expires_at)
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.email_verification_code_hash == "verification-hash"
    assert stored_user.email_verification_code_expires_at == expires_at
    assert stored_user.email_verification_attempts == 0

    await db.increment_email_verification_attempts(user.id)
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.email_verification_attempts == 1

    await db.clear_email_verification_code(user.id)
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.email_verification_code_hash is None
    assert stored_user.email_verification_code_expires_at is None
    assert stored_user.email_verification_attempts == 0

    await db.set_email_verification_code(user.id, "verification-hash", expires_at)
    await db.mark_web_user_email_verified(user.id)
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.email_verified is True
    assert stored_user.email_verification_code_hash is None
    assert stored_user.email_verification_code_expires_at is None
    assert stored_user.email_verification_attempts == 0


async def test_password_reset_state_updates_password_and_attempts() -> None:
    user = _build_user(email="reset@example.com")
    await db.create_web_user(user)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await db.set_password_reset_code(user.id, "reset-hash", expires_at)
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.password_reset_code_hash == "reset-hash"
    assert stored_user.password_reset_code_expires_at == expires_at
    assert stored_user.password_reset_attempts == 0

    await db.increment_password_reset_attempts(user.id)
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.password_reset_attempts == 1

    await db.update_web_user_password_hash(user.id, "new-password-hash")
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.password_hash == "new-password-hash"

    await db.clear_password_reset_code(user.id)
    stored_user = await db.get_web_user_by_id(user.id)
    assert stored_user is not None
    assert stored_user.password_reset_code_hash is None
    assert stored_user.password_reset_code_expires_at is None
    assert stored_user.password_reset_attempts == 0
