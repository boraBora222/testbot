# Task: Profile Documents API and Access Rules

- Objective: Define and implement the backend contract for listing, uploading, downloading, and deleting client documents with strict authorization and validation behavior.
- Owner: Dev
- Dependencies: [Documents and compliance specification](../../specifications/documents_and_compliance), `01-domain-model-and-storage-foundation.md`, existing profile authorization flow, and existing backend material handlers where reuse is appropriate
- Success Criteria:
  - `GET /api/profile/documents` returns the user's profile documents with stable metadata fields.
  - `POST /api/profile/documents` accepts a client document upload through the web backend flow.
  - `DELETE /api/profile/documents/{document_id}` removes only documents that belong to the authenticated user.
  - `GET /api/profile/documents/{document_id}/download` returns a temporary download link instead of the file body.
  - Invalid format, oversized files, unauthorized access, and missing documents have explicit error behavior.

## Steps

1. Define the response contract for profile documents.
```text
- Return `id`, `type`, `fileName`, `fileSize`, and `createdAt` for every document item.
- Include enough metadata for the profile UI to render type, file name, upload date, and size directly.
- Keep type values stable so i18n labels can be resolved consistently in the client.
```

2. Implement the list and upload endpoints.
```text
- Add `GET /api/profile/documents` for the authenticated user's document list.
- Add `POST /api/profile/documents` for client document upload through the web flow.
- Apply format and size validation before storage and persistence work begins.
- Make replacement for the same `client_doc_type` explicit instead of leaving duplicate active records.
```

3. Implement delete and download-link flows.
```text
- Add `DELETE /api/profile/documents/{document_id}` with ownership checks before deletion.
- Add `GET /api/profile/documents/{document_id}/download` that returns a presigned URL payload.
- Keep the backend responsible for authorization and link issuance, not for proxying the file body.
```

4. Enforce access-control and error rules.
```text
- Require authorization for every endpoint in this task.
- Return `403` when a user attempts to access another user's document.
- Return `404` when the document does not exist in the allowed scope.
- Return `400` for unsupported format or size violations.
```

5. Align repository and service boundaries.
```text
- Reuse the shared material/document repository contract from `01`.
- Keep API behavior explicit about replacement, delete, and download semantics.
- Do not introduce fallback paths that bypass document ownership or storage-backed downloads.
```

## Validation

- Review sections `4.1`, `5`, `8.1`, and `8.3` of the specification and confirm each endpoint requirement is covered.
- Confirm the API never returns public permanent links or direct file payloads for download operations.
- Confirm ownership checks are described as mandatory for list, delete, and download flows.
