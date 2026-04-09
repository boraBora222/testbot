"""Canonical exchange service-facade entry points.

New exchange code should prefer importing these named facades from
``shared.services`` instead of reaching into implementation modules directly.
Existing direct imports remain supported during the transition.
"""

from __future__ import annotations

from . import documents, order_lifecycle, security_settings


class OrderService:
    """Facade for exchange order, draft, and read-model workflows."""

    validate_order_payload = staticmethod(order_lifecycle.validate_order_payload)
    build_order_from_payload = staticmethod(order_lifecycle.build_order_from_payload)
    build_order_draft = staticmethod(order_lifecycle.build_order_draft)
    build_order_state_from_draft = staticmethod(order_lifecycle.build_order_state_from_draft)
    build_order_list_item = staticmethod(order_lifecycle.build_order_list_item)
    build_order_detail_payload = staticmethod(order_lifecycle.build_order_detail_payload)
    build_repeat_seed = staticmethod(order_lifecycle.build_repeat_seed)
    build_status_meta = staticmethod(order_lifecycle.build_status_meta)
    can_repeat_order = staticmethod(order_lifecycle.can_repeat_order)
    get_status_filter_values = staticmethod(order_lifecycle.get_status_filter_values)
    normalize_order_filter = staticmethod(order_lifecycle.normalize_order_filter)
    normalize_order_status = staticmethod(order_lifecycle.normalize_order_status)


class ProfileService:
    """Facade for exchange whitelist, quota, and moderation workflows."""

    WhitelistApprovalRequiredError = security_settings.WhitelistApprovalRequiredError
    LimitQuotaNotConfiguredError = security_settings.LimitQuotaNotConfiguredError
    build_default_whitelist_label = staticmethod(security_settings.build_default_whitelist_label)
    create_pending_whitelist_entry = staticmethod(security_settings.create_pending_whitelist_entry)
    resolve_order_whitelist_payload = staticmethod(security_settings.resolve_order_whitelist_payload)
    create_order_with_security_checks = staticmethod(security_settings.create_order_with_security_checks)
    update_limit_quota_with_audit = staticmethod(security_settings.update_limit_quota_with_audit)
    moderate_whitelist_address_with_audit = staticmethod(security_settings.moderate_whitelist_address_with_audit)


class DocumentService:
    """Facade for exchange document workflows."""

    ProfileDocumentValidationError = documents.ProfileDocumentValidationError
    ProfileDocumentStorageUnavailableError = documents.ProfileDocumentStorageUnavailableError
    ProfileDocumentPersistenceError = documents.ProfileDocumentPersistenceError
    ProfileDocumentStoredFileMissingError = documents.ProfileDocumentStoredFileMissingError
    ProfileDocumentDownloadUnavailableError = documents.ProfileDocumentDownloadUnavailableError
    DealDocumentValidationError = documents.DealDocumentValidationError
    DealDocumentStorageUnavailableError = documents.DealDocumentStorageUnavailableError
    DealDocumentPersistenceError = documents.DealDocumentPersistenceError
    DealDocumentStoredFileMissingError = documents.DealDocumentStoredFileMissingError
    DealDocumentDownloadUnavailableError = documents.DealDocumentDownloadUnavailableError
    audit_document_event = staticmethod(documents.audit_document_event)
    store_profile_document_upload = staticmethod(documents.store_profile_document_upload)
    issue_profile_document_download_link = staticmethod(documents.issue_profile_document_download_link)
    delete_stored_profile_document = staticmethod(documents.delete_stored_profile_document)
    store_deal_document_upload = staticmethod(documents.store_deal_document_upload)
    issue_deal_document_download_link = staticmethod(documents.issue_deal_document_download_link)


order_service = OrderService()
profile_service = ProfileService()
document_service = DocumentService()

WhitelistApprovalRequiredError = security_settings.WhitelistApprovalRequiredError
LimitQuotaNotConfiguredError = security_settings.LimitQuotaNotConfiguredError

__all__ = [
    "DocumentService",
    "LimitQuotaNotConfiguredError",
    "OrderService",
    "ProfileService",
    "WhitelistApprovalRequiredError",
    "document_service",
    "documents",
    "order_lifecycle",
    "order_service",
    "profile_service",
    "security_settings",
]
