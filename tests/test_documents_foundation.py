from copy import deepcopy
from datetime import datetime, timezone
import json
import logging

import pymongo
import pytest
from pydantic import ValidationError

from shared import db
from shared.models import MaterialDB
from shared.services import documents as document_service
from shared.services.storage import DocumentStorageMissingObjectError, PresignedObjectUrl
from shared.types.enums import ClientDocumentType, DealDocumentType, MaterialContentType


class _InsertResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class _DeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class _Cursor:
    def __init__(self, documents: list[dict]) -> None:
        self._documents = [deepcopy(document) for document in documents]

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, list):
            sort_pairs = key_or_list
        else:
            sort_pairs = [(key_or_list, direction)]
        for key, sort_direction in reversed(sort_pairs):
            reverse = sort_direction == pymongo.DESCENDING
            self._documents.sort(key=lambda document: document.get(key), reverse=reverse)
        return self

    async def __aiter__(self):
        for document in self._documents:
            yield deepcopy(document)


class _MaterialsCollection:
    def __init__(self, seed_documents: list[dict] | None = None) -> None:
        self.documents = [deepcopy(document) for document in (seed_documents or [])]
        self.index_calls: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.index_calls.append((keys, kwargs))
        return f"idx_{len(self.index_calls)}"

    async def insert_one(self, payload: dict):
        stored = deepcopy(payload)
        stored.setdefault("_id", f"mongo_{len(self.documents) + 1}")
        self.documents.append(stored)
        return _InsertResult(stored["_id"])

    async def find_one(self, filters: dict, projection=None):
        for document in self.documents:
            if all(document.get(field_name) == field_value for field_name, field_value in filters.items()):
                return deepcopy(document)
        return None

    async def find_one_and_replace(self, filters: dict, replacement: dict, upsert: bool, return_document):
        for index, document in enumerate(self.documents):
            if all(document.get(field_name) == field_value for field_name, field_value in filters.items()):
                stored = deepcopy(replacement)
                stored["_id"] = document.get("_id", f"mongo_{index + 1}")
                self.documents[index] = stored
                return deepcopy(stored)
        if not upsert:
            return None
        stored = deepcopy(replacement)
        stored["_id"] = f"mongo_{len(self.documents) + 1}"
        self.documents.append(stored)
        return deepcopy(stored)

    async def delete_one(self, filters: dict):
        for index, document in enumerate(self.documents):
            if all(document.get(field_name) == field_value for field_name, field_value in filters.items()):
                self.documents.pop(index)
                return _DeleteResult(1)
        return _DeleteResult(0)

    def find(self, filters: dict):
        matched = [
            deepcopy(document)
            for document in self.documents
            if all(document.get(field_name) == field_value for field_name, field_value in filters.items())
        ]
        return _Cursor(matched)


class _LinksCollection:
    def __init__(self) -> None:
        self.inserted: list[dict] = []
        self.index_calls: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.index_calls.append((keys, kwargs))
        return f"idx_{len(self.index_calls)}"

    async def insert_one(self, payload: dict):
        self.inserted.append(deepcopy(payload))
        return _InsertResult(f"link_{len(self.inserted)}")


class _GenericCollection:
    def __init__(self) -> None:
        self.index_calls: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.index_calls.append((keys, kwargs))
        return f"idx_{len(self.index_calls)}"


class _FakeDatabase:
    def __init__(self, materials: _MaterialsCollection | None = None, links: _LinksCollection | None = None) -> None:
        self.materials = materials or _MaterialsCollection()
        self.links = links or _LinksCollection()
        self.bot_users = _GenericCollection()
        self.users = _GenericCollection()
        self.banned_users = _GenericCollection()
        self.website_submissions = _GenericCollection()
        self.support_messages = _GenericCollection()
        self.orders = _GenericCollection()
        self.order_drafts = _GenericCollection()
        self.limit_quotas = _GenericCollection()
        self.limit_quota_history = _GenericCollection()
        self.whitelist_addresses = _GenericCollection()


class _FakeStorageClient:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []
        self.deletes: list[tuple[str, bool]] = []
        self.missing_keys: set[str] = set()

    async def upload_bytes(self, *, object_key: str, payload: bytes, content_type: str) -> None:
        self.uploads.append((object_key, payload, content_type))

    async def delete_object(self, *, object_key: str, missing_ok: bool = False) -> None:
        self.deletes.append((object_key, missing_ok))

    async def ensure_object_exists(self, *, object_key: str) -> None:
        if object_key in self.missing_keys:
            raise DocumentStorageMissingObjectError("Document object not found.")

    def build_presigned_download_url(self, *, object_key: str, expires_in_seconds: int) -> PresignedObjectUrl:
        return PresignedObjectUrl(
            url=f"https://storage.example/{object_key}?expires={expires_in_seconds}",
            expires_at=datetime.now(timezone.utc).replace(microsecond=0),
        )


def _read_audit_payloads(caplog: pytest.LogCaptureFixture) -> list[dict]:
    payloads: list[dict] = []
    for record in caplog.records:
        message = record.getMessage()
        if not message.startswith("document_audit "):
            continue
        payloads.append(json.loads(message.removeprefix("document_audit ")))
    return payloads


def test_material_content_type_and_document_enums_match_spec() -> None:
    assert MaterialContentType.CLIENT_DOC.value == "client_doc"
    assert MaterialContentType.DEAL_DOC.value == "deal_doc"
    assert [item.value for item in ClientDocumentType] == [
        "inn",
        "ogrn",
        "charter",
        "protocol",
        "director_passport",
        "egrul_extract",
        "bank_details",
        "other",
    ]
    assert [item.value for item in DealDocumentType] == [
        "contract",
        "act",
        "confirmation",
        "other",
    ]


def test_material_db_accepts_file_id_alias_and_persists_telegram_file_id() -> None:
    material = MaterialDB(
        user_id=321,
        content_type=MaterialContentType.DOCUMENT,
        file_id="telegram-file-1",
        file_name="support.pdf",
        mime_type="application/pdf",
    )

    payload = material.model_dump()

    assert material.telegram_file_id == "telegram-file-1"
    assert material.file_id == "telegram-file-1"
    assert payload["telegram_file_id"] == "telegram-file-1"
    assert "file_id" not in payload


def test_material_db_requires_document_metadata_for_client_documents() -> None:
    with pytest.raises(ValidationError, match="s3_key is required for document records"):
        MaterialDB(
            user_id=321,
            content_type=MaterialContentType.CLIENT_DOC,
            client_doc_type=ClientDocumentType.INN,
            file_name="inn.pdf",
            mime_type="application/pdf",
            file_size=2048,
        )


def test_material_db_requires_deal_id_for_deal_documents() -> None:
    with pytest.raises(ValidationError, match="deal_id is required for DEAL_DOC records"):
        MaterialDB(
            user_id=321,
            content_type=MaterialContentType.DEAL_DOC,
            deal_doc_type=DealDocumentType.CONTRACT,
            file_name="contract.pdf",
            mime_type="application/pdf",
            file_size=4096,
            s3_key="documents/deals/deal-1/contract.pdf",
        )


def test_build_deal_document_s3_key_keeps_deal_scope_and_type() -> None:
    key = document_service.build_deal_document_s3_key(
        deal_id="deal-42",
        deal_doc_type=DealDocumentType.CONTRACT,
        file_name="Contract Final.pdf",
        uploaded_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
    )

    assert key.startswith("documents/deals/deal-42/contract/20260403T120000Z-")
    assert key.endswith("-Contract-Final.pdf")


@pytest.mark.anyio
async def test_create_material_skips_legacy_mirroring_for_profile_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = _FakeDatabase()
    monkeypatch.setattr(db, "get_db", lambda: fake_db)

    material = MaterialDB(
        user_id=321,
        content_type=MaterialContentType.CLIENT_DOC,
        client_doc_type=ClientDocumentType.INN,
        file_name="inn.pdf",
        mime_type="application/pdf",
        file_size=1024,
        s3_key="documents/users/321/inn.pdf",
    )

    material_id = await db.create_material(material)

    assert material_id == material.id
    assert len(fake_db.materials.documents) == 1
    assert fake_db.links.inserted == []
    assert fake_db.materials.documents[0]["telegram_file_id"] is None


@pytest.mark.anyio
async def test_create_or_replace_client_document_reuses_same_logical_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = _FakeDatabase(materials=_MaterialsCollection())
    monkeypatch.setattr(db, "get_db", lambda: fake_db)

    first_document = MaterialDB(
        user_id=321,
        content_type=MaterialContentType.CLIENT_DOC,
        client_doc_type=ClientDocumentType.CHARTER,
        file_name="charter-v1.pdf",
        mime_type="application/pdf",
        file_size=1024,
        s3_key="documents/users/321/charter-v1.pdf",
        created_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
    )
    second_document = MaterialDB(
        user_id=321,
        content_type=MaterialContentType.CLIENT_DOC,
        client_doc_type=ClientDocumentType.CHARTER,
        file_name="charter-v2.pdf",
        mime_type="application/pdf",
        file_size=2048,
        s3_key="documents/users/321/charter-v2.pdf",
        created_at=datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc),
    )

    saved_first = await db.create_or_replace_client_document(first_document)
    saved_second = await db.create_or_replace_client_document(second_document)

    assert saved_first["id"] == first_document.id
    assert saved_second["id"] == saved_first["id"]
    assert len(fake_db.materials.documents) == 1
    assert fake_db.materials.documents[0]["file_name"] == "charter-v2.pdf"
    assert fake_db.materials.documents[0]["s3_key"] == "documents/users/321/charter-v2.pdf"


@pytest.mark.anyio
async def test_list_deal_documents_filters_by_deal_and_sorts_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = _FakeDatabase(
        materials=_MaterialsCollection(
            [
                {
                    "_id": "mongo_1",
                    "id": "mat_1",
                    "user_id": 321,
                    "content_type": MaterialContentType.DEAL_DOC.value,
                    "deal_doc_type": DealDocumentType.CONTRACT.value,
                    "deal_id": "deal-1",
                    "file_name": "contract.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 200,
                    "s3_key": "documents/deals/deal-1/contract.pdf",
                    "created_at": datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc),
                },
                {
                    "_id": "mongo_2",
                    "id": "mat_2",
                    "user_id": 321,
                    "content_type": MaterialContentType.DEAL_DOC.value,
                    "deal_doc_type": DealDocumentType.ACT.value,
                    "deal_id": "deal-1",
                    "file_name": "act.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 300,
                    "s3_key": "documents/deals/deal-1/act.pdf",
                    "created_at": datetime(2026, 4, 3, 9, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 3, 9, 0, tzinfo=timezone.utc),
                },
                {
                    "_id": "mongo_3",
                    "id": "mat_3",
                    "user_id": 321,
                    "content_type": MaterialContentType.DEAL_DOC.value,
                    "deal_doc_type": DealDocumentType.CONFIRMATION.value,
                    "deal_id": "deal-2",
                    "file_name": "confirmation.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 300,
                    "s3_key": "documents/deals/deal-2/confirmation.pdf",
                    "created_at": datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
                },
            ]
        )
    )
    monkeypatch.setattr(db, "get_db", lambda: fake_db)

    documents = await db.list_deal_documents("deal-1", user_id=321)

    assert [document["id"] for document in documents] == ["mat_2", "mat_1"]


@pytest.mark.anyio
async def test_store_prepared_profile_document_rolls_back_uploaded_object_on_db_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_storage = _FakeStorageClient()

    async def fake_get_profile_document_by_type(user_id: int, client_doc_type: str):
        return None

    async def fake_create_or_replace_client_document(material):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    monkeypatch.setattr(db, "get_profile_document_by_type", fake_get_profile_document_by_type)
    monkeypatch.setattr(db, "create_or_replace_client_document", fake_create_or_replace_client_document)

    prepared = document_service.PreparedProfileDocumentUpload(
        file_name="inn.pdf",
        mime_type="application/pdf",
        file_size=7,
        s3_key="documents/users/321/inn/20260403T120000Z-test-inn.pdf",
        content=b"payload",
    )

    with pytest.raises(document_service.ProfileDocumentPersistenceError, match="Profile document could not be saved"):
        await document_service.store_prepared_profile_document(
            user_id=321,
            username="client321",
            first_name="Client",
            client_doc_type=ClientDocumentType.INN,
            prepared_upload=prepared,
        )

    assert fake_storage.uploads == [
        ("documents/users/321/inn/20260403T120000Z-test-inn.pdf", b"payload", "application/pdf")
    ]
    assert fake_storage.deletes == [("documents/users/321/inn/20260403T120000Z-test-inn.pdf", True)]


@pytest.mark.anyio
async def test_store_prepared_profile_document_writes_upload_audit_entry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_storage = _FakeStorageClient()

    async def fake_get_profile_document_by_type(user_id: int, client_doc_type: str):
        assert user_id == 321
        assert client_doc_type == ClientDocumentType.INN.value
        return None

    async def fake_create_or_replace_client_document(material):
        return {
            "id": "mat_inn",
            "user_id": material.user_id,
            "client_doc_type": material.client_doc_type.value,
            "file_name": material.file_name,
            "file_size": material.file_size,
            "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            "s3_key": material.s3_key,
        }

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    monkeypatch.setattr(db, "get_profile_document_by_type", fake_get_profile_document_by_type)
    monkeypatch.setattr(db, "create_or_replace_client_document", fake_create_or_replace_client_document)
    caplog.set_level(logging.INFO, logger=document_service.__name__)

    stored = await document_service.store_prepared_profile_document(
        user_id=321,
        username="client321",
        first_name="Client",
        client_doc_type=ClientDocumentType.INN,
        prepared_upload=document_service.PreparedProfileDocumentUpload(
            file_name="inn.pdf",
            mime_type="application/pdf",
            file_size=7,
            s3_key="documents/users/321/inn/20260403T120000Z-test-inn.pdf",
            content=b"payload",
        ),
    )

    audits = _read_audit_payloads(caplog)

    assert stored.replaced is False
    assert {
        "action": "upload",
        "outcome": "success",
        "scope": "profile",
        "user_id": 321,
        "document_id": "mat_inn",
        "client_doc_type": "inn",
        "file_name": "inn.pdf",
        "replaced": False,
        "s3_key": "documents/users/321/inn/20260403T120000Z-test-inn.pdf",
    } in audits


@pytest.mark.anyio
async def test_store_prepared_profile_document_writes_replace_audit_entry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_storage = _FakeStorageClient()

    async def fake_get_profile_document_by_type(user_id: int, client_doc_type: str):
        assert user_id == 321
        assert client_doc_type == ClientDocumentType.CHARTER.value
        return {
            "id": "mat_charter",
            "user_id": 321,
            "client_doc_type": "charter",
            "file_name": "charter-v1.pdf",
            "s3_key": "documents/users/321/charter/20260403T110000Z-old-charter.pdf",
        }

    async def fake_create_or_replace_client_document(material):
        return {
            "id": "mat_charter",
            "user_id": material.user_id,
            "client_doc_type": material.client_doc_type.value,
            "file_name": material.file_name,
            "file_size": material.file_size,
            "created_at": datetime(2026, 4, 3, 13, 0, tzinfo=timezone.utc),
            "s3_key": material.s3_key,
        }

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    monkeypatch.setattr(db, "get_profile_document_by_type", fake_get_profile_document_by_type)
    monkeypatch.setattr(db, "create_or_replace_client_document", fake_create_or_replace_client_document)
    caplog.set_level(logging.INFO, logger=document_service.__name__)

    stored = await document_service.store_prepared_profile_document(
        user_id=321,
        username="client321",
        first_name="Client",
        client_doc_type=ClientDocumentType.CHARTER,
        prepared_upload=document_service.PreparedProfileDocumentUpload(
            file_name="charter-v2.pdf",
            mime_type="application/pdf",
            file_size=8,
            s3_key="documents/users/321/charter/20260403T130000Z-new-charter.pdf",
            content=b"payload-v2",
        ),
    )

    audits = _read_audit_payloads(caplog)

    assert stored.replaced is True
    assert ("documents/users/321/charter/20260403T110000Z-old-charter.pdf", True) in fake_storage.deletes
    assert {
        "action": "replace",
        "outcome": "success",
        "scope": "profile",
        "user_id": 321,
        "document_id": "mat_charter",
        "client_doc_type": "charter",
        "file_name": "charter-v2.pdf",
        "replaced": True,
        "s3_key": "documents/users/321/charter/20260403T130000Z-new-charter.pdf",
    } in audits


@pytest.mark.anyio
async def test_store_prepared_deal_document_rolls_back_uploaded_object_on_db_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_storage = _FakeStorageClient()

    async def fake_create_deal_document(material):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    monkeypatch.setattr(db, "create_deal_document", fake_create_deal_document)

    prepared = document_service.PreparedDealDocumentUpload(
        file_name="contract.pdf",
        mime_type="application/pdf",
        file_size=7,
        s3_key="documents/deals/ORD-001/contract/20260403T120000Z-test-contract.pdf",
        content=b"payload",
    )

    with pytest.raises(document_service.DealDocumentPersistenceError, match="Deal document could not be saved"):
        await document_service.store_prepared_deal_document(
            user_id=321,
            username="client321",
            first_name=None,
            deal_id="ORD-001",
            deal_doc_type=DealDocumentType.CONTRACT,
            prepared_upload=prepared,
        )

    assert fake_storage.uploads == [
        ("documents/deals/ORD-001/contract/20260403T120000Z-test-contract.pdf", b"payload", "application/pdf")
    ]
    assert fake_storage.deletes == [("documents/deals/ORD-001/contract/20260403T120000Z-test-contract.pdf", True)]


@pytest.mark.anyio
async def test_store_prepared_deal_document_writes_deal_link_audit_entry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_storage = _FakeStorageClient()

    async def fake_create_deal_document(material):
        return {
            "id": "mat_contract",
            "user_id": material.user_id,
            "deal_id": material.deal_id,
            "deal_doc_type": material.deal_doc_type.value,
            "file_name": material.file_name,
            "file_size": material.file_size,
            "created_at": datetime(2026, 4, 3, 12, 30, tzinfo=timezone.utc),
            "s3_key": material.s3_key,
        }

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    monkeypatch.setattr(db, "create_deal_document", fake_create_deal_document)
    caplog.set_level(logging.INFO, logger=document_service.__name__)

    stored = await document_service.store_prepared_deal_document(
        user_id=321,
        username="client321",
        first_name=None,
        deal_id="ORD-001",
        deal_doc_type=DealDocumentType.CONTRACT,
        prepared_upload=document_service.PreparedDealDocumentUpload(
            file_name="contract.pdf",
            mime_type="application/pdf",
            file_size=7,
            s3_key="documents/deals/ORD-001/contract/20260403T123000Z-contract.pdf",
            content=b"payload",
        ),
    )

    audits = _read_audit_payloads(caplog)

    assert stored.document["id"] == "mat_contract"
    assert {
        "action": "deal_link",
        "outcome": "success",
        "scope": "deal",
        "user_id": 321,
        "deal_id": "ORD-001",
        "document_id": "mat_contract",
        "deal_doc_type": "contract",
        "file_name": "contract.pdf",
        "s3_key": "documents/deals/ORD-001/contract/20260403T123000Z-contract.pdf",
    } in audits


@pytest.mark.anyio
async def test_transfer_profile_document_from_telegram_uses_shared_storage_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_storage = _FakeStorageClient()
    captured = {"telegram_file_id": None}

    async def fake_download_telegram_file_content(*, telegram_file_id: str) -> bytes:
        assert telegram_file_id == "telegram-file-1"
        return b"%PDF-1.4"

    async def fake_get_profile_document_by_type(user_id: int, client_doc_type: str):
        return None

    async def fake_create_or_replace_client_document(material):
        captured["telegram_file_id"] = material.telegram_file_id
        return {
            "id": "mat_inn",
            "user_id": material.user_id,
            "client_doc_type": material.client_doc_type.value,
            "file_name": material.file_name,
            "file_size": material.file_size,
            "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            "s3_key": material.s3_key,
            "telegram_file_id": material.telegram_file_id,
        }

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    monkeypatch.setattr(document_service, "download_telegram_file_content", fake_download_telegram_file_content)
    monkeypatch.setattr(db, "get_profile_document_by_type", fake_get_profile_document_by_type)
    monkeypatch.setattr(db, "create_or_replace_client_document", fake_create_or_replace_client_document)

    stored = await document_service.transfer_profile_document_from_telegram(
        user_id=321,
        username="client321",
        first_name="Client",
        client_doc_type=ClientDocumentType.INN,
        telegram_file_id="telegram-file-1",
        file_name="inn.pdf",
    )

    assert stored.replaced is False
    assert stored.document["id"] == "mat_inn"
    assert captured["telegram_file_id"] == "telegram-file-1"
    assert len(fake_storage.uploads) == 1
    assert fake_storage.uploads[0][2] == "application/pdf"


def test_build_profile_document_download_link_generates_15_minute_presigned_ttl() -> None:
    storage = document_service.get_document_storage()

    link = storage.build_presigned_download_url(
        object_key="documents/users/321/inn/inn.pdf",
        expires_in_seconds=document_service.PROFILE_DOCUMENT_DOWNLOAD_TTL_SECONDS,
    )

    assert link.url.startswith("http://localhost:9000/documents/documents/users/321/inn/inn.pdf?")
    assert "X-Amz-Expires=900" in link.url
    ttl = int((link.expires_at - datetime.now(timezone.utc)).total_seconds())
    assert 890 <= ttl <= 900


def test_build_deal_document_download_link_generates_15_minute_presigned_ttl() -> None:
    storage = document_service.get_document_storage()

    link = storage.build_presigned_download_url(
        object_key="documents/deals/ORD-001/contract/contract.pdf",
        expires_in_seconds=document_service.DEAL_DOCUMENT_DOWNLOAD_TTL_SECONDS,
    )

    assert link.url.startswith("http://localhost:9000/documents/documents/deals/ORD-001/contract/contract.pdf?")
    assert "X-Amz-Expires=900" in link.url
    ttl = int((link.expires_at - datetime.now(timezone.utc)).total_seconds())
    assert 890 <= ttl <= 900


@pytest.mark.anyio
async def test_issue_profile_document_download_link_raises_missing_file_error_for_missing_storage_object(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_storage = _FakeStorageClient()
    fake_storage.missing_keys.add("documents/users/321/inn/inn.pdf")

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    caplog.set_level(logging.INFO, logger=document_service.__name__)

    with pytest.raises(document_service.ProfileDocumentStoredFileMissingError, match="Stored profile document file is missing"):
        await document_service.issue_profile_document_download_link(
            s3_key="documents/users/321/inn/inn.pdf",
        )

    assert {
        "action": "download",
        "outcome": "failure",
        "scope": "profile",
        "s3_key": "documents/users/321/inn/inn.pdf",
        "reason": "stored_object_missing",
    } in _read_audit_payloads(caplog)


@pytest.mark.anyio
async def test_issue_deal_document_download_link_raises_missing_file_error_for_missing_storage_object(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_storage = _FakeStorageClient()
    fake_storage.missing_keys.add("documents/deals/ORD-001/contract/contract.pdf")

    monkeypatch.setattr(document_service, "get_document_storage", lambda: fake_storage)
    caplog.set_level(logging.INFO, logger=document_service.__name__)

    with pytest.raises(document_service.DealDocumentStoredFileMissingError, match="Stored deal document file is missing"):
        await document_service.issue_deal_document_download_link(
            s3_key="documents/deals/ORD-001/contract/contract.pdf",
        )

    assert {
        "action": "download",
        "outcome": "failure",
        "scope": "deal",
        "s3_key": "documents/deals/ORD-001/contract/contract.pdf",
        "reason": "stored_object_missing",
    } in _read_audit_payloads(caplog)


@pytest.mark.anyio
async def test_ensure_indexes_registers_document_specific_indexes() -> None:
    fake_db = _FakeDatabase()

    await db._ensure_indexes(fake_db)

    material_indexes = fake_db.materials.index_calls
    assert any(keys == [("created_at", pymongo.DESCENDING)] for keys, _ in material_indexes)
    assert any(
        keys == [("user_id", pymongo.ASCENDING), ("content_type", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)]
        for keys, _ in material_indexes
    )
    assert any(
        keys == [("deal_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)]
        and kwargs.get("partialFilterExpression") == {"deal_id": {"$exists": True, "$type": "string"}}
        for keys, kwargs in material_indexes
    )
    assert any(
        keys == [("user_id", pymongo.ASCENDING), ("client_doc_type", pymongo.ASCENDING)]
        and kwargs.get("unique") is True
        and kwargs.get("partialFilterExpression") == {"content_type": MaterialContentType.CLIENT_DOC.value}
        for keys, kwargs in material_indexes
    )
