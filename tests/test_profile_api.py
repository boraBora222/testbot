from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging

import pytest
from fastapi.testclient import TestClient

from shared import db
from shared.models import AuthSessionDB, LimitQuotaDB, WhitelistAddressDB, WebUserDB
from shared.services.documents import DocumentDownloadLink, StoredProfileDocument
from shared.security_settings import next_daily_reset_at, next_monthly_reset_at
from shared.types.enums import VerificationLevel
from web.config import settings
from web.routers import profile as profile_router


def _authenticate_web_user(client: TestClient, *, linked_exchange_user_id: int | None) -> WebUserDB:
    user = WebUserDB(
        id="user_profile_test",
        email="profile@example.com",
        password_hash="hash",
        linked_exchange_user_id=linked_exchange_user_id,
    )
    session = AuthSessionDB(
        session_id="profile_session_test",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db._web_users[user.email] = user
    db._auth_sessions[session.session_id] = session
    client.cookies.set(settings.auth_cookie_name, session.session_id)
    return user


def _read_audit_payloads(caplog: pytest.LogCaptureFixture) -> list[dict]:
    payloads: list[dict] = []
    for record in caplog.records:
        message = record.getMessage()
        if not message.startswith("document_audit "):
            continue
        payloads.append(json.loads(message.removeprefix("document_audit ")))
    return payloads


def test_profile_limits_requires_explicit_exchange_link(app_client: TestClient) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=None)

    response = app_client.get("/api/profile/limits")

    assert response.status_code == 409
    assert response.json()["detail"] == "Current web account is not linked to an exchange user."


def test_get_profile_limits_returns_daily_and_monthly_contract(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    quota = LimitQuotaDB(
        user_id=321,
        verification_level=VerificationLevel.EXTENDED,
        daily_limit=Decimal("10000000"),
        daily_used=Decimal("1250000"),
        daily_reset_at=next_daily_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
        monthly_limit=Decimal("50000000"),
        monthly_used=Decimal("12345678"),
        monthly_reset_at=next_monthly_reset_at(datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)),
        updated_at=datetime(2026, 4, 3, 10, 30, tzinfo=timezone.utc),
    )

    async def fake_get_limit_quota(user_id: int):
        assert user_id == 321
        return quota.model_dump()

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321, "notification_preferences": {}}

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_limit_quota", fake_get_limit_quota)

    response = app_client.get("/api/profile/limits")

    assert response.status_code == 200
    payload = response.json()
    assert payload["verification_level"] == "extended"
    assert payload["daily_limit"] == "10000000"
    assert payload["daily_used"] == "1250000"
    assert payload["daily_remaining"] == "8750000"
    assert payload["monthly_limit"] == "50000000"
    assert payload["monthly_used"] == "12345678"
    assert payload["monthly_remaining"] == "37654322"
    assert payload["daily_reset_at"] in {"2026-04-04T00:00:00Z", "2026-04-04T00:00:00+00:00"}
    assert payload["monthly_reset_at"] in {"2026-05-01T00:00:00Z", "2026-05-01T00:00:00+00:00"}
    assert payload["updated_at"] in {"2026-04-03T10:30:00Z", "2026-04-03T10:30:00+00:00"}


def test_get_profile_limits_fails_fast_when_quota_is_missing(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_limit_quota(user_id: int):
        assert user_id == 321
        return None

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_limit_quota", fake_get_limit_quota)

    response = app_client.get("/api/profile/limits")

    assert response.status_code == 409
    assert response.json()["detail"] == "Limit quota is not configured for current exchange user."


def test_get_profile_notifications_returns_current_preferences(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {
            "telegram_user_id": 321,
            "notification_preferences": {
                "telegram_enabled": True,
                "email_enabled": False,
                "events": {
                    "order_created": True,
                    "order_status_changed": True,
                    "support_reply": False,
                    "limit_warning": True,
                },
            },
        }

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)

    response = app_client.get("/api/profile/notifications")

    assert response.status_code == 200
    assert response.json() == {
        "telegram_enabled": True,
        "email_enabled": False,
        "events": {
            "order_created": True,
            "order_status_changed": True,
            "support_reply": False,
            "limit_warning": True,
        },
    }


def test_profile_api_adds_request_timing_headers(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {
            "telegram_user_id": 321,
            "notification_preferences": {
                "telegram_enabled": True,
                "email_enabled": True,
                "events": {
                    "order_created": True,
                    "order_status_changed": True,
                    "support_reply": True,
                    "limit_warning": False,
                },
            },
        }

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)

    response = app_client.get("/api/profile/notifications")

    assert response.status_code == 200
    assert response.headers["x-request-id"] != ""
    assert response.headers["server-timing"].startswith("app;dur=")


def test_get_profile_notifications_fails_fast_when_contract_is_missing(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321}

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)

    response = app_client.get("/api/profile/notifications")

    assert response.status_code == 409
    assert response.json()["detail"] == "Notification preferences are not configured for current exchange user."


def test_put_profile_notifications_persists_supported_settings(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    captured = {"preferences": None}

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_update_exchange_user_notification_preferences(user_id: int, preferences):
        assert user_id == 321
        captured["preferences"] = preferences
        return True

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "update_exchange_user_notification_preferences", fake_update_exchange_user_notification_preferences)

    response = app_client.put(
        "/api/profile/notifications",
        json={
            "telegram_enabled": False,
            "email_enabled": True,
            "events": {
                "order_created": False,
                "order_status_changed": True,
                "support_reply": True,
                "limit_warning": False,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["telegram_enabled"] is False
    assert response.json()["email_enabled"] is True
    assert captured["preferences"] is not None
    assert captured["preferences"].telegram_enabled is False
    assert captured["preferences"].events.limit_warning is False


def test_put_profile_notifications_rejects_unsupported_event_keys(app_client: TestClient) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    response = app_client.put(
        "/api/profile/notifications",
        json={
            "telegram_enabled": True,
            "email_enabled": True,
            "events": {
                "order_created": True,
                "order_status_changed": True,
                "support_reply": True,
                "limit_warning": True,
                "marketing": True,
            },
        },
    )

    assert response.status_code == 422


def test_put_profile_notifications_rejects_non_boolean_channel_values(app_client: TestClient) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    response = app_client.put(
        "/api/profile/notifications",
        json={
            "telegram_enabled": "yes",
            "email_enabled": True,
            "events": {
                "order_created": True,
                "order_status_changed": True,
                "support_reply": True,
                "limit_warning": True,
            },
        },
    )

    assert response.status_code == 422


def test_get_profile_documents_returns_stable_metadata_contract(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_list_profile_documents(user_id: int):
        assert user_id == 321
        return [
            {
                "id": "mat_new",
                "user_id": 321,
                "client_doc_type": "charter",
                "file_name": "charter.pdf",
                "file_size": 2048,
                "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            },
            {
                "id": "mat_old",
                "user_id": 321,
                "client_doc_type": "inn",
                "file_name": "inn.pdf",
                "file_size": 1024,
                "created_at": datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc),
            },
        ]

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "list_profile_documents", fake_list_profile_documents)

    response = app_client.get("/api/profile/documents")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "mat_new"
    assert payload[0]["type"] == "charter"
    assert payload[0]["fileName"] == "charter.pdf"
    assert payload[0]["fileSize"] == 2048
    assert payload[0]["createdAt"] in {"2026-04-03T12:00:00Z", "2026-04-03T12:00:00+00:00"}
    assert "s3_key" not in payload[0]
    assert "downloadUrl" not in payload[0]
    assert payload[1]["id"] == "mat_old"
    assert payload[1]["type"] == "inn"
    assert payload[1]["fileName"] == "inn.pdf"
    assert payload[1]["fileSize"] == 1024
    assert payload[1]["createdAt"] in {"2026-04-03T11:00:00Z", "2026-04-03T11:00:00+00:00"}
    assert "s3_key" not in payload[1]
    assert "downloadUrl" not in payload[1]


def test_post_profile_documents_uploads_new_document_and_returns_created(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    captured = {"upload": None}

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {
            "telegram_user_id": 321,
            "username": "client321",
            "first_name": "Client",
            "notification_preferences": {},
        }

    async def fake_store_profile_document_upload(*, user_id: int, username, first_name, client_doc_type, upload):
        assert user_id == 321
        assert username == "client321"
        assert first_name == "Client"
        assert client_doc_type.value == "inn"
        assert upload.filename == "inn.pdf"
        captured["upload"] = upload
        return StoredProfileDocument(
            document={
                "id": "mat_inn",
                "user_id": 321,
                "client_doc_type": "inn",
                "file_name": "inn.pdf",
                "file_size": 1536,
                "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                "s3_key": "documents/users/321/inn/20260403T120000Z-inn.pdf",
            },
            replaced=False,
        )

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(profile_router.document_service, "store_profile_document_upload", fake_store_profile_document_upload)

    response = app_client.post(
        "/api/profile/documents",
        data={"type": "inn"},
        files={"file": ("inn.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == "mat_inn"
    assert payload["type"] == "inn"
    assert payload["fileName"] == "inn.pdf"
    assert payload["fileSize"] == 1536
    assert payload["createdAt"] in {"2026-04-03T12:00:00Z", "2026-04-03T12:00:00+00:00"}
    assert "s3_key" not in payload
    assert "downloadUrl" not in payload
    assert captured["upload"] is not None
    assert captured["upload"].filename == "inn.pdf"


def test_post_profile_documents_returns_ok_when_replacing_same_type(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_store_profile_document_upload(*, user_id: int, username, first_name, client_doc_type, upload):
        return StoredProfileDocument(
            document={
                "id": "mat_charter",
                "user_id": 321,
                "client_doc_type": client_doc_type.value,
                "file_name": "charter-v2.pdf",
                "file_size": 4096,
                "created_at": datetime(2026, 4, 3, 13, 0, tzinfo=timezone.utc),
                "s3_key": "documents/users/321/charter/20260403T130000Z-charter-v2.pdf",
            },
            replaced=True,
        )

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(profile_router.document_service, "store_profile_document_upload", fake_store_profile_document_upload)

    response = app_client.post(
        "/api/profile/documents",
        data={"type": "charter"},
        files={"file": ("charter-v2.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "mat_charter"
    assert response.json()["type"] == "charter"


def test_post_profile_documents_rejects_unsupported_format_with_400(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)

    response = app_client.post(
        "/api/profile/documents",
        data={"type": "inn"},
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported profile document format."


def test_post_profile_documents_rejects_oversized_file_with_400(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(profile_router.document_service, "PROFILE_DOCUMENT_MAX_SIZE_BYTES", 32)

    response = app_client.post(
        "/api/profile/documents",
        data={"type": "inn"},
        files={"file": ("inn.pdf", b"x" * 33, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Profile documents must be 10 MB or smaller."


def test_post_profile_documents_returns_503_when_storage_upload_fails(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_store_profile_document_upload(*, user_id: int, username, first_name, client_doc_type, upload):
        raise profile_router.document_service.ProfileDocumentStorageUnavailableError(
            "Profile document storage is temporarily unavailable."
        )

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(profile_router.document_service, "store_profile_document_upload", fake_store_profile_document_upload)

    response = app_client.post(
        "/api/profile/documents",
        data={"type": "inn"},
        files={"file": ("inn.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Profile document storage is temporarily unavailable."


def test_delete_profile_document_returns_403_for_foreign_document(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_profile_document(document_id: str):
        assert document_id == "mat_foreign"
        return {
            "id": "mat_foreign",
            "user_id": 999,
            "s3_key": "documents/users/999/inn/foreign.pdf",
        }

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_profile_document", fake_get_profile_document)

    response = app_client.delete("/api/profile/documents/mat_foreign")

    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have access to this profile document."


def test_delete_profile_document_returns_404_when_missing(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_profile_document(document_id: str):
        assert document_id == "mat_missing"
        return None

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_profile_document", fake_get_profile_document)

    response = app_client.delete("/api/profile/documents/mat_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile document not found."


def test_delete_profile_document_deletes_owned_document(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_profile_document(document_id: str):
        return {
            "id": "mat_inn",
            "user_id": 321,
            "s3_key": "documents/users/321/inn/inn.pdf",
        }

    async def fake_delete_profile_document(user_id: int, document_id: str):
        assert user_id == 321
        assert document_id == "mat_inn"
        return True

    async def fake_delete_stored_profile_document(*, s3_key: str):
        assert s3_key == "documents/users/321/inn/inn.pdf"

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_profile_document", fake_get_profile_document)
    monkeypatch.setattr(db, "delete_profile_document", fake_delete_profile_document)
    monkeypatch.setattr(profile_router.document_service, "delete_stored_profile_document", fake_delete_stored_profile_document)
    caplog.set_level(logging.INFO, logger=profile_router.document_service.__name__)

    response = app_client.delete("/api/profile/documents/mat_inn")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Profile document deleted successfully."}
    assert {
        "action": "delete",
        "outcome": "success",
        "scope": "profile",
        "user_id": 321,
        "document_id": "mat_inn",
        "s3_key": "documents/users/321/inn/inn.pdf",
    } in _read_audit_payloads(caplog)


def test_get_profile_document_download_returns_temporary_link_for_owner(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_profile_document(document_id: str):
        assert document_id == "mat_inn"
        return {
            "id": "mat_inn",
            "user_id": 321,
            "client_doc_type": "inn",
            "s3_key": "documents/users/321/inn/inn.pdf",
        }

    async def fake_issue_profile_document_download_link(*, s3_key: str):
        assert s3_key == "documents/users/321/inn/inn.pdf"
        return DocumentDownloadLink(
            download_url="https://localhost:9000/documents/users/321/inn/inn.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256",
            expires_at=datetime(2026, 4, 3, 12, 15, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_profile_document", fake_get_profile_document)
    monkeypatch.setattr(profile_router.document_service, "issue_profile_document_download_link", fake_issue_profile_document_download_link)
    caplog.set_level(logging.INFO, logger=profile_router.document_service.__name__)

    response = app_client.get("/api/profile/documents/mat_inn/download")

    assert response.status_code == 200
    payload = response.json()
    assert payload["downloadUrl"] == "https://localhost:9000/documents/users/321/inn/inn.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    assert payload["expiresAt"] in {"2026-04-03T12:15:00Z", "2026-04-03T12:15:00+00:00"}
    assert "s3_key" not in payload
    assert {
        "action": "download",
        "outcome": "success",
        "scope": "profile",
        "user_id": 321,
        "document_id": "mat_inn",
        "client_doc_type": "inn",
        "s3_key": "documents/users/321/inn/inn.pdf",
    } in _read_audit_payloads(caplog)


def test_get_profile_document_download_returns_404_when_stored_object_is_missing(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_profile_document(document_id: str):
        return {
            "id": "mat_inn",
            "user_id": 321,
            "s3_key": "documents/users/321/inn/inn.pdf",
        }

    async def fake_issue_profile_document_download_link(*, s3_key: str):
        raise profile_router.document_service.ProfileDocumentStoredFileMissingError(
            "Stored profile document file is missing."
        )

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_profile_document", fake_get_profile_document)
    monkeypatch.setattr(profile_router.document_service, "issue_profile_document_download_link", fake_issue_profile_document_download_link)

    response = app_client.get("/api/profile/documents/mat_inn/download")

    assert response.status_code == 404
    assert response.json()["detail"] == "Stored profile document file is missing."


def test_get_profile_document_download_returns_503_when_storage_is_unavailable(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_profile_document(document_id: str):
        return {
            "id": "mat_inn",
            "user_id": 321,
            "s3_key": "documents/users/321/inn/inn.pdf",
        }

    async def fake_issue_profile_document_download_link(*, s3_key: str):
        raise profile_router.document_service.ProfileDocumentDownloadUnavailableError(
            "Profile document download is temporarily unavailable."
        )

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_profile_document", fake_get_profile_document)
    monkeypatch.setattr(profile_router.document_service, "issue_profile_document_download_link", fake_issue_profile_document_download_link)

    response = app_client.get("/api/profile/documents/mat_inn/download")

    assert response.status_code == 503
    assert response.json()["detail"] == "Profile document download is temporarily unavailable."


def test_get_profile_document_download_returns_403_for_foreign_document(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_profile_document(document_id: str):
        return {
            "id": "mat_foreign",
            "user_id": 777,
            "s3_key": "documents/users/777/inn/foreign.pdf",
        }

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_profile_document", fake_get_profile_document)
    caplog.set_level(logging.INFO, logger=profile_router.document_service.__name__)

    response = app_client.get("/api/profile/documents/mat_foreign/download")

    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have access to this profile document."
    assert {
        "action": "download",
        "outcome": "denied",
        "scope": "profile",
        "user_id": 321,
        "owner_user_id": 777,
        "document_id": "mat_foreign",
        "s3_key": "documents/users/777/inn/foreign.pdf",
        "reason": "owner_mismatch",
    } in _read_audit_payloads(caplog)


def test_get_profile_whitelist_returns_current_entries(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    whitelist_entry = WhitelistAddressDB(
        id="wla_1",
        user_id=321,
        network="TRC20",
        address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        label="Main treasury",
    )

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_list_whitelist_addresses_for_user(user_id: int):
        assert user_id == 321
        return [whitelist_entry.model_dump()]

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "list_whitelist_addresses_for_user", fake_list_whitelist_addresses_for_user)

    response = app_client.get("/api/profile/whitelist")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "wla_1"
    assert payload[0]["network"] == "TRC-20"
    assert payload[0]["status"] == "pending"


def test_post_profile_whitelist_creates_pending_entry(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    captured = {"entry": None}

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_list_whitelist_addresses_for_user(user_id: int):
        assert user_id == 321
        return []

    async def fake_create_whitelist_address(entry: WhitelistAddressDB):
        captured["entry"] = entry
        return entry

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "list_whitelist_addresses_for_user", fake_list_whitelist_addresses_for_user)
    monkeypatch.setattr(db, "create_whitelist_address", fake_create_whitelist_address)

    response = app_client.post(
        "/api/profile/whitelist",
        json={
            "network": "ERC20",
            "address": "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "label": "Hot wallet",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert captured["entry"] is not None
    assert captured["entry"].network == "ERC-20"
    assert captured["entry"].address_normalized == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_post_profile_whitelist_rejects_resubmission_of_rejected_address(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        assert user_id == 321
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_list_whitelist_addresses_for_user(user_id: int):
        assert user_id == 321
        return [
            {
                "id": "wla_rejected",
                "user_id": 321,
                "network": "ERC-20",
                "address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "address_normalized": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "label": "Rejected",
                "status": "rejected",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        ]

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "list_whitelist_addresses_for_user", fake_list_whitelist_addresses_for_user)

    response = app_client.post(
        "/api/profile/whitelist",
        json={
            "network": "ERC20",
            "address": "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            "label": "Retry",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected whitelist addresses cannot be submitted again."


def test_put_profile_whitelist_updates_label_only(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_update_whitelist_address_label(user_id: int, whitelist_id: str, label: str):
        assert user_id == 321
        assert whitelist_id == "wla_1"
        assert label == "Treasury"
        return WhitelistAddressDB(
            id="wla_1",
            user_id=321,
            network="TRC20",
            address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            label=label,
        ).model_dump()

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "update_whitelist_address_label", fake_update_whitelist_address_label)

    response = app_client.put("/api/profile/whitelist/wla_1", json={"label": "Treasury"})

    assert response.status_code == 200
    assert response.json()["label"] == "Treasury"


def test_delete_profile_whitelist_rejects_entry_used_by_active_order(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)
    entry = WhitelistAddressDB(
        id="wla_1",
        user_id=321,
        network="TRC20",
        address="TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        label="Main",
    )

    async def fake_get_exchange_user(user_id: int):
        return {"telegram_user_id": 321, "notification_preferences": {}}

    async def fake_get_whitelist_address_for_user(user_id: int, whitelist_id: str):
        assert user_id == 321
        assert whitelist_id == "wla_1"
        return entry.model_dump()

    async def fake_count_active_orders_for_whitelist_address(**kwargs):
        return 1

    monkeypatch.setattr(db, "get_exchange_user", fake_get_exchange_user)
    monkeypatch.setattr(db, "get_whitelist_address_for_user", fake_get_whitelist_address_for_user)
    monkeypatch.setattr(db, "count_active_orders_for_whitelist_address", fake_count_active_orders_for_whitelist_address)

    response = app_client.delete("/api/profile/whitelist/wla_1")

    assert response.status_code == 409
    assert response.json()["detail"] == "Whitelist entry is used by an active order and cannot be deleted."
