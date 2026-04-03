# Task: Audit, Validation, and Release Readiness

- Objective: Finalize audit coverage, functional and non-functional validation, and release sign-off for the documents and compliance MVP.
- Owner: Dev + QA
- Dependencies: `01-domain-model-and-storage-foundation.md`, `02-profile-documents-api-and-access-rules.md`, `03-storage-integration-and-file-lifecycle.md`, `04-telegram-bot-client-document-flow.md`, `05-web-profile-documents-ui.md`, `06-deal-documents-api-and-deal-card-integration.md`
- Success Criteria:
  - Audit coverage exists for upload, download, delete, replacement, and deal-link actions.
  - MVP acceptance criteria can be checked directly against implemented bot, web, and deal flows.
  - Non-functional requirements for storage, access control, link TTL, and error handling are explicitly verified.
  - Release-readiness review covers backend, storage, Telegram bot, and web UI behavior.

## Steps

1. Verify audit coverage.
```text
- Ensure audit logging covers upload, download, delete, replacement, and deal-document attachment actions.
- Check that log records contain enough context to investigate failures or unauthorized access attempts.
- Keep audit behavior aligned with the MVP scope instead of inventing extra lifecycle events not present in the specification.
```

2. Execute functional acceptance validation.
```text
- Verify client document upload through Telegram bot.
- Verify client document upload through web.
- Verify S3/MinIO-backed persistence and profile list rendering.
- Verify same-type document replacement for profile documents.
- Verify the deal card loads documents from the real API instead of mocks.
- Verify profile and deal document downloads work through temporary links.
- Verify access to foreign documents is denied.
```

3. Execute non-functional validation.
```text
- Verify supported format enforcement.
- Verify the 10 MB size limit.
- Verify presigned URL TTL is 15 minutes.
- Verify there are no public permanent links in stored data or user flows.
- Verify storage, Telegram-transfer, and missing-file failures produce clear errors.
```

4. Prepare release sign-off.
```text
- Convert sections `12` and `13` of the specification into a release checklist.
- Confirm excluded scope is still excluded:
  no moderation, no PDF generation, no template generation,
  no lifecycle statuses, no EDI integration, no versioning, and no separate company entity.
- Record any operational assumptions required for deployment of S3/MinIO-backed document storage.
```

## Validation

- Review sections `5`, `11`, `12`, `13`, and `14` of the specification and confirm every MVP readiness point is represented in the checklist.
- Confirm the release checklist covers both happy-path usage and enforcement-path failures.
- Confirm the package remains inside MVP boundaries and does not silently expand scope.
