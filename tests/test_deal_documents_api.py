from datetime import datetime, timedelta, timezone
import json
import logging

import pytest
from fastapi.testclient import TestClient

from shared import db
from shared.models import AuthSessionDB, WebUserDB
from shared.services.documents import DocumentDownloadLink, StoredDealDocument
from web.config import settings
from web.routers import deals as deals_router


def _authenticate_web_user(client: TestClient, *, linked_exchange_user_id: int | None) -> WebUserDB:
    user = WebUserDB(
        id="user_deal_docs_test",
        email="deal-docs@example.com",
        password_hash="hash",
        linked_exchange_user_id=linked_exchange_user_id,
    )
    session = AuthSessionDB(
        session_id="deal_docs_session_test",
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


def test_list_deal_documents_returns_stable_metadata_contract(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    async def fake_list_deal_documents(deal_id: str, user_id: int | None = None):
        assert deal_id == "ORD-001"
        assert user_id == 321
        return [
            {
                "id": "mat_contract",
                "deal_doc_type": "contract",
                "file_name": "contract.pdf",
                "file_size": 2048,
                "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            },
            {
                "id": "mat_act",
                "deal_doc_type": "act",
                "file_name": "act.pdf",
                "file_size": 1024,
                "created_at": datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc),
            },
        ]

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(db, "list_deal_documents", fake_list_deal_documents)

    response = app_client.get("/api/deals/ORD-001/documents")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "mat_contract"
    assert payload[0]["type"] == "contract"
    assert payload[0]["fileName"] == "contract.pdf"
    assert payload[0]["fileSize"] == 2048
    assert payload[0]["createdAt"] in {"2026-04-03T12:00:00Z", "2026-04-03T12:00:00+00:00"}
    assert "s3_key" not in payload[0]
    assert "downloadUrl" not in payload[0]
    assert payload[1]["id"] == "mat_act"
    assert payload[1]["type"] == "act"
    assert payload[1]["fileName"] == "act.pdf"
    assert payload[1]["fileSize"] == 1024
    assert payload[1]["createdAt"] in {"2026-04-03T11:00:00Z", "2026-04-03T11:00:00+00:00"}
    assert "s3_key" not in payload[1]
    assert "downloadUrl" not in payload[1]


def test_list_deal_documents_returns_403_for_inaccessible_deal(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-FOREIGN"
        assert user_id == 321
        return None

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)

    response = app_client.get("/api/deals/ORD-FOREIGN/documents")

    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have access to this deal."


def test_post_deal_documents_attaches_prepared_file(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321, "username": "client321"}

    async def fake_store_deal_document_upload(*, user_id: int, username, first_name, deal_id: str, deal_doc_type, upload):
        assert user_id == 321
        assert username == "client321"
        assert first_name is None
        assert deal_id == "ORD-001"
        assert deal_doc_type.value == "contract"
        assert upload.filename == "contract.pdf"
        return StoredDealDocument(
            document={
                "id": "mat_contract",
                "deal_doc_type": "contract",
                "file_name": "contract.pdf",
                "file_size": 3072,
                "created_at": datetime(2026, 4, 3, 12, 30, tzinfo=timezone.utc),
                "s3_key": "documents/deals/ORD-001/contract/20260403T123000Z-contract.pdf",
            }
        )

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(deals_router.document_service, "store_deal_document_upload", fake_store_deal_document_upload)

    response = app_client.post(
        "/api/deals/ORD-001/documents",
        data={"type": "contract"},
        files={"file": ("contract.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == "mat_contract"
    assert payload["type"] == "contract"
    assert payload["fileName"] == "contract.pdf"
    assert payload["fileSize"] == 3072
    assert payload["createdAt"] in {"2026-04-03T12:30:00Z", "2026-04-03T12:30:00+00:00"}
    assert "s3_key" not in payload
    assert "downloadUrl" not in payload


def test_get_deal_document_download_returns_temporary_link(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    async def fake_get_deal_document(deal_id: str, document_id: str, user_id: int | None = None):
        assert deal_id == "ORD-001"
        assert document_id == "mat_contract"
        assert user_id == 321
        return {
            "id": "mat_contract",
            "deal_id": deal_id,
            "user_id": 321,
            "deal_doc_type": "contract",
            "s3_key": "documents/deals/ORD-001/contract/contract.pdf",
        }

    async def fake_issue_deal_document_download_link(*, s3_key: str):
        assert s3_key == "documents/deals/ORD-001/contract/contract.pdf"
        return DocumentDownloadLink(
            download_url="https://localhost:9000/documents/deals/ORD-001/contract/contract.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256",
            expires_at=datetime(2026, 4, 3, 12, 45, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(db, "get_deal_document", fake_get_deal_document)
    monkeypatch.setattr(deals_router.document_service, "issue_deal_document_download_link", fake_issue_deal_document_download_link)
    caplog.set_level(logging.INFO, logger=deals_router.document_service.__name__)

    response = app_client.get("/api/deals/ORD-001/documents/mat_contract/download")

    assert response.status_code == 200
    payload = response.json()
    assert payload["downloadUrl"] == "https://localhost:9000/documents/deals/ORD-001/contract/contract.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    assert payload["expiresAt"] in {"2026-04-03T12:45:00Z", "2026-04-03T12:45:00+00:00"}
    assert "s3_key" not in payload
    assert {
        "action": "download",
        "outcome": "success",
        "scope": "deal",
        "user_id": 321,
        "deal_id": "ORD-001",
        "document_id": "mat_contract",
        "deal_doc_type": "contract",
        "s3_key": "documents/deals/ORD-001/contract/contract.pdf",
    } in _read_audit_payloads(caplog)


def test_get_deal_document_download_returns_403_for_inaccessible_deal_and_audits_attempt(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-FOREIGN"
        assert user_id == 321
        return None

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    caplog.set_level(logging.INFO, logger=deals_router.document_service.__name__)

    response = app_client.get("/api/deals/ORD-FOREIGN/documents/mat_contract/download")

    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have access to this deal."
    assert {
        "action": "download",
        "outcome": "denied",
        "scope": "deal",
        "user_id": 321,
        "deal_id": "ORD-FOREIGN",
        "reason": "deal_access_denied",
    } in _read_audit_payloads(caplog)


def test_get_deal_document_download_returns_404_when_document_is_missing_in_scope(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    async def fake_get_deal_document(deal_id: str, document_id: str, user_id: int | None = None):
        assert deal_id == "ORD-001"
        assert document_id == "mat_missing"
        assert user_id == 321
        return None

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(db, "get_deal_document", fake_get_deal_document)

    response = app_client.get("/api/deals/ORD-001/documents/mat_missing/download")

    assert response.status_code == 404
    assert response.json()["detail"] == "Deal document not found."


def test_post_deal_documents_rejects_unsupported_format_with_400(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)

    response = app_client.post(
        "/api/deals/ORD-001/documents",
        data={"type": "contract"},
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported deal document format."


def test_post_deal_documents_rejects_oversized_file_with_400(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(deals_router.document_service, "DEAL_DOCUMENT_MAX_SIZE_BYTES", 32)

    response = app_client.post(
        "/api/deals/ORD-001/documents",
        data={"type": "contract"},
        files={"file": ("contract.pdf", b"x" * 33, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Deal documents must be 10 MB or smaller."


def test_post_deal_documents_returns_503_when_storage_upload_fails(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    async def fake_store_deal_document_upload(*, user_id: int, username, first_name, deal_id: str, deal_doc_type, upload):
        raise deals_router.document_service.DealDocumentStorageUnavailableError(
            "Deal document storage is temporarily unavailable."
        )

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(deals_router.document_service, "store_deal_document_upload", fake_store_deal_document_upload)

    response = app_client.post(
        "/api/deals/ORD-001/documents",
        data={"type": "contract"},
        files={"file": ("contract.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Deal document storage is temporarily unavailable."


def test_get_deal_document_download_returns_404_when_stored_object_is_missing(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    async def fake_get_deal_document(deal_id: str, document_id: str, user_id: int | None = None):
        assert deal_id == "ORD-001"
        assert document_id == "mat_contract"
        assert user_id == 321
        return {
            "id": "mat_contract",
            "deal_id": deal_id,
            "user_id": 321,
            "s3_key": "documents/deals/ORD-001/contract/contract.pdf",
        }

    async def fake_issue_deal_document_download_link(*, s3_key: str):
        raise deals_router.document_service.DealDocumentStoredFileMissingError(
            "Stored deal document file is missing."
        )

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(db, "get_deal_document", fake_get_deal_document)
    monkeypatch.setattr(deals_router.document_service, "issue_deal_document_download_link", fake_issue_deal_document_download_link)

    response = app_client.get("/api/deals/ORD-001/documents/mat_contract/download")

    assert response.status_code == 404
    assert response.json()["detail"] == "Stored deal document file is missing."


def test_get_deal_document_download_returns_503_when_storage_is_unavailable(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticate_web_user(app_client, linked_exchange_user_id=321)

    async def fake_get_order_for_user(order_id: str, user_id: int):
        assert order_id == "ORD-001"
        assert user_id == 321
        return {"order_id": order_id, "user_id": 321}

    async def fake_get_deal_document(deal_id: str, document_id: str, user_id: int | None = None):
        assert deal_id == "ORD-001"
        assert document_id == "mat_contract"
        assert user_id == 321
        return {
            "id": "mat_contract",
            "deal_id": deal_id,
            "user_id": 321,
            "s3_key": "documents/deals/ORD-001/contract/contract.pdf",
        }

    async def fake_issue_deal_document_download_link(*, s3_key: str):
        raise deals_router.document_service.DealDocumentDownloadUnavailableError(
            "Deal document download is temporarily unavailable."
        )

    monkeypatch.setattr(db, "get_order_for_user", fake_get_order_for_user)
    monkeypatch.setattr(db, "get_deal_document", fake_get_deal_document)
    monkeypatch.setattr(deals_router.document_service, "issue_deal_document_download_link", fake_issue_deal_document_download_link)

    response = app_client.get("/api/deals/ORD-001/documents/mat_contract/download")

    assert response.status_code == 503
    assert response.json()["detail"] == "Deal document download is temporarily unavailable."
