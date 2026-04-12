from datetime import datetime, timedelta, timezone

import pytest

from shared import db
from shared.models import AuthSessionDB, LimitQuotaDB, WebUserDB, build_default_notification_preferences
from shared.security_settings import next_daily_reset_at, next_monthly_reset_at
from shared.types.enums import VerificationLevel

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


async def test_exchange_user_storage_supports_in_memory_fallback_and_notification_updates() -> None:
    initial_preferences = build_default_notification_preferences().model_copy(
        update={
            "telegram_enabled": False,
            "email_enabled": True,
        }
    )
    await db.ensure_exchange_user(
        telegram_user_id=-101,
        username=None,
        first_name="Web",
        last_name="User",
        create_bot_user=False,
        notification_preferences=initial_preferences,
    )

    stored_user = await db.get_exchange_user(-101)
    assert stored_user is not None
    assert stored_user["telegram_user_id"] == -101
    assert stored_user["first_name"] == "Web"
    assert stored_user["last_name"] == "User"
    assert stored_user["notification_preferences"]["telegram_enabled"] is False
    assert stored_user["notification_preferences"]["email_enabled"] is True

    updated_preferences = build_default_notification_preferences().model_copy(
        update={
            "telegram_enabled": False,
            "email_enabled": False,
        }
    )
    assert await db.update_exchange_user_notification_preferences(-101, updated_preferences) is True

    refreshed_user = await db.get_exchange_user(-101)
    assert refreshed_user is not None
    assert refreshed_user["notification_preferences"]["telegram_enabled"] is False
    assert refreshed_user["notification_preferences"]["email_enabled"] is False


async def test_limit_quota_storage_supports_in_memory_fallback_and_usage_updates() -> None:
    quota = LimitQuotaDB(
        user_id=-101,
        verification_level=VerificationLevel.BASIC,
        daily_limit=1000000,
        daily_used=0,
        daily_reset_at=next_daily_reset_at(datetime.now(timezone.utc)),
        monthly_limit=5000000,
        monthly_used=0,
        monthly_reset_at=next_monthly_reset_at(datetime.now(timezone.utc)),
    )

    saved_quota = await db.upsert_limit_quota(quota)
    assert saved_quota == quota

    stored_quota = await db.get_limit_quota(-101)
    assert stored_quota is not None
    assert stored_quota["verification_level"] == VerificationLevel.BASIC
    assert stored_quota["daily_limit"] == 1000000
    assert stored_quota["monthly_limit"] == 5000000

    updated_quota = await db.increment_limit_quota_usage(-101, 250000)
    assert updated_quota is not None
    assert updated_quota.daily_used == 250000
    assert updated_quota.monthly_used == 250000


async def test_limit_quota_upsert_uses_non_conflicting_mongo_update(monkeypatch: pytest.MonkeyPatch) -> None:
    quota = LimitQuotaDB(
        user_id=-202,
        verification_level=VerificationLevel.BASIC,
        daily_limit=1000000,
        daily_used=0,
        daily_reset_at=next_daily_reset_at(datetime.now(timezone.utc)),
        monthly_limit=5000000,
        monthly_used=0,
        monthly_reset_at=next_monthly_reset_at(datetime.now(timezone.utc)),
    )

    class FakeLimitQuotaCollection:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def find_one_and_update(self, filters, update, *, upsert, return_document):
            self.calls.append(
                {
                    "filters": filters,
                    "update": update,
                    "upsert": upsert,
                    "return_document": return_document,
                }
            )
            return {
                "_id": "quota_doc",
                **update["$set"],
            }

    class FakeDatabase:
        def __init__(self) -> None:
            self.limit_quotas = FakeLimitQuotaCollection()

    fake_database = FakeDatabase()
    monkeypatch.setattr(db, "_get_db_if_available", lambda: fake_database)

    saved_quota = await db.upsert_limit_quota(quota)

    assert saved_quota == quota
    assert fake_database.limit_quotas.calls == [
        {
            "filters": {"user_id": -202},
            "update": fake_database.limit_quotas.calls[0]["update"],
            "upsert": True,
            "return_document": fake_database.limit_quotas.calls[0]["return_document"],
        }
    ]
    assert "$set" in fake_database.limit_quotas.calls[0]["update"]
    assert "$setOnInsert" not in fake_database.limit_quotas.calls[0]["update"]
    assert fake_database.limit_quotas.calls[0]["update"]["$set"]["user_id"] == -202
