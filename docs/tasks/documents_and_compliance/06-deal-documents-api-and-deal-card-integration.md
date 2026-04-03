# Task: Deal Documents API and Deal Card Integration

- Objective: Replace the mock deal-documents section with real backend document data and enforce deal-scoped access control for list and download operations.
- Owner: Dev
- Dependencies: [Documents and compliance specification](../../specifications/documents_and_compliance), `01-domain-model-and-storage-foundation.md`, `02-profile-documents-api-and-access-rules.md`, `03-storage-integration-and-file-lifecycle.md`, current deal access rules, and the existing deal-card documents placeholder
- Success Criteria:
  - `GET /api/deals/{deal_id}/documents` returns documents linked to the requested deal.
  - `GET /api/deals/{deal_id}/documents/{document_id}/download` returns a temporary storage-backed link after access checks.
  - `POST /api/deals/{deal_id}/documents` supports attaching prepared files to a deal through the backend/admin flow.
  - The deal card uses real API data instead of mocks.
  - Users cannot access documents for deals outside their allowed scope.

## Steps

1. Define the deal-document backend contract.
```text
- Implement `GET /api/deals/{deal_id}/documents`.
- Implement `GET /api/deals/{deal_id}/documents/{document_id}/download`.
- Implement `POST /api/deals/{deal_id}/documents` for prepared-file attachment in the MVP backend/admin flow.
- Keep the response contract aligned with the shared metadata fields:
  `id`, `type`, `fileName`, `fileSize`, and `createdAt`.
```

2. Persist and query deal linkage.
```text
- Use `deal_id` as the required linkage field for `DEAL_DOC`.
- Restrict deal document queries to the requested deal scope.
- Keep document type classification explicit for `contract`, `act`, `confirmation`, and `other`.
```

3. Enforce deal access control.
```text
- Check that the authenticated user has access to the requested deal before list or download succeeds.
- Return `403` for foreign or inaccessible deal documents.
- Return `404` when the document does not exist in the allowed deal scope.
```

4. Replace the mock deal-card documents section.
```text
- Remove the current dependency on mock deal-document data.
- Load the deal-card documents tab from the real deal-document API.
- Render document type, file name, date added, and size from backend metadata.
```

5. Keep download behavior storage-backed and explicit.
```text
- Issue presigned URLs through the backend after access validation.
- Keep prepared deal documents downloadable from S3/MinIO, not from local placeholders or public links.
- Do not add generation, templating, or lifecycle statuses that are explicitly out of MVP scope.
```

## Validation

- Review sections `4.2`, `5`, `8.2`, `8.3`, `9.3`, `10.4`, and `10.5` of the specification and confirm the deal-document behavior is covered.
- Confirm the deal card no longer depends on mock document data.
- Confirm deal-level access checks are mandatory for both list and download operations.
