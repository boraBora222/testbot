# Task: Storage Integration and File Lifecycle

- Objective: Implement the S3/MinIO-backed file lifecycle for document upload, storage, replacement, and download-link generation across bot, web, and deal-document flows.
- Owner: Dev
- Dependencies: [Documents and compliance specification](../../specifications/documents_and_compliance), `01-domain-model-and-storage-foundation.md`, existing storage configuration surfaces, and current Telegram file-download capability
- Success Criteria:
  - S3/MinIO is the primary storage for downloadable documents.
  - Database records store `s3_key` and metadata only.
  - Bot-uploaded documents are transferred from Telegram to S3/MinIO before they become downloadable.
  - Download links are issued as presigned URLs with a 15-minute TTL.
  - Storage and transfer failures are handled explicitly and surfaced as user-facing errors through the calling flow.

## Steps

1. Define the document storage contract.
```text
- Configure one document bucket or document storage namespace for the MVP.
- Define deterministic object-key rules that distinguish profile documents from deal documents.
- Keep the stored source of truth as `s3_key` plus metadata in the database.
```

2. Implement upload and replacement behavior.
```text
- Add a storage abstraction that uploads validated files to S3/MinIO.
- Ensure replacement of the same `client_doc_type` updates the active record and stored object association cleanly.
- Keep storage writes and database writes coordinated so incomplete state is not treated as success.
```

3. Implement Telegram-to-storage transfer.
```text
- Download the original file from Telegram using the available `file_id`.
- Upload the retrieved file to S3/MinIO before confirming success to the user.
- Preserve `telegram_file_id` only as source metadata for bot-upload flows, not as the primary download source.
```

4. Implement storage-backed download issuance.
```text
- Generate presigned URLs for document downloads.
- Enforce the 15-minute TTL requirement.
- Keep download behavior private and authorization-gated through backend link issuance.
```

5. Define explicit failure handling and observability.
```text
- Handle Telegram download failure explicitly.
- Handle S3/MinIO upload failure explicitly.
- Handle missing stored object and download-link generation failure explicitly.
- Log storage errors with enough context for diagnosis and do not downgrade them into silent fallback behavior.
```

## Validation

- Review sections `1.3`, `5`, `6.2`, `6.3`, `6.4`, and `9.4` of the specification and confirm the storage lifecycle matches the MVP architecture.
- Confirm the database does not persist `s3_url` or any public permanent file link.
- Confirm bot-upload and web-upload flows both terminate in the same storage-backed download behavior.
