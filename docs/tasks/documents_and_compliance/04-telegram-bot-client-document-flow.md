# Task: Telegram Bot Client Document Flow

- Objective: Add a Telegram bot flow that lets the user upload client documents with the same validation, storage, and replacement semantics as the backend profile-document contract.
- Owner: Dev
- Dependencies: [Documents and compliance specification](../../specifications/documents_and_compliance), `01-domain-model-and-storage-foundation.md`, `02-profile-documents-api-and-access-rules.md`, `03-storage-integration-and-file-lifecycle.md`, and the existing Telegram document-processing flow
- Success Criteria:
  - The user can upload a supported client document through the Telegram bot.
  - Format and size validation follow the same MVP rules as the web flow.
  - The bot persists the document as `CLIENT_DOC` and stores the file in S3/MinIO.
  - Re-upload of the same `client_doc_type` replaces the previous active document.
  - The bot returns a clear success message or a clear error message for supported failure cases.

## Steps

1. Reuse the existing bot document entry path.
```text
- Extend the current Telegram document-handling flow instead of creating a parallel upload subsystem.
- Add an explicit client-document scenario that captures the required document type and authenticated user context.
- Keep the stored material classification as `CLIENT_DOC`.
```

2. Apply validation before persistence.
```text
- Accept only the supported formats from the specification:
  PDF, DOC, DOCX, XLS, XLSX, JPG, and PNG.
- Reject files over 10 MB before the upload is confirmed.
- Return a user-facing error that states the real failure reason.
```

3. Transfer the file into the shared storage pipeline.
```text
- Resolve Telegram `file_id` and fetch the source file.
- Upload the file into S3/MinIO through the shared storage abstraction from `03`.
- Persist the document record only after storage succeeds.
```

4. Apply replacement and confirmation behavior.
```text
- Replace the user's previous active document for the same `client_doc_type`.
- Confirm successful upload after the database record is created.
- Keep replacement behavior explicit so the bot does not imply version history exists in MVP.
```

5. Cover expected bot-side failures.
```text
- Handle unsupported format.
- Handle oversized file.
- Handle Telegram download failure.
- Handle S3/MinIO upload failure.
- Keep all failure messages clear and tied to the actual failed step.
```

## Validation

- Review sections `4.1`, `6.2`, `9.2`, `10.1`, and `11` of the specification and confirm the bot flow covers all required steps.
- Confirm the bot does not leave Telegram as the primary download source after upload completes.
- Confirm bot validation and replacement behavior matches the profile-document backend contract.
