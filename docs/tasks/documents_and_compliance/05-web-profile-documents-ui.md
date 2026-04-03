# Task: Web Profile Documents UI

- Objective: Add the profile documents section in the web dashboard with upload, list, download, and delete flows backed by the real profile documents API.
- Owner: Dev
- Dependencies: [Documents and compliance specification](../../specifications/documents_and_compliance), `02-profile-documents-api-and-access-rules.md`, `03-storage-integration-and-file-lifecycle.md`, and the existing profile/dashboard UI surface
- Success Criteria:
  - The profile page has a real documents section for the authenticated user.
  - The user can upload a supported document through the web UI.
  - The UI lists document type, file name, upload date, and size.
  - The user can download and delete profile documents from the UI.
  - Re-upload of the same `client_doc_type` refreshes the list with the replacement result.

## Steps

1. Add the profile documents section.
```text
- Add a dedicated documents block to the profile/dashboard surface.
- Load the list from `GET /api/profile/documents`.
- Keep the empty state explicit rather than hiding the feature when no documents exist.
```

2. Implement the upload flow.
```text
- Wire the upload action to `POST /api/profile/documents`.
- Validate supported formats and the 10 MB limit before or during submission, without weakening backend validation.
- Refresh the list after a successful upload so replacement behavior is visible immediately.
```

3. Render metadata and localized document types.
```text
- Display type, file name, upload date, and size for each document row.
- Resolve type labels through ru/en i18n mapping instead of hardcoding one language into enum values.
- Keep UI labels aligned with the stable backend `type` contract.
```

4. Implement download and delete actions.
```text
- Use `GET /api/profile/documents/{document_id}/download` to request a temporary link.
- Use `DELETE /api/profile/documents/{document_id}` for removal.
- Update the list after deletion so the UI stays consistent with backend state.
```

5. Surface user-facing errors clearly.
```text
- Show clear messages for unsupported format, oversized file, upload failure, missing file, and access denial.
- Keep error text tied to the real backend result instead of replacing it with ambiguous generic wording.
- Do not imply partial success when upload or delete fails.
```

## Validation

- Review sections `4.1`, `8.1`, `9.3`, and `10.2` through `10.3` of the specification and confirm the profile UI covers each required user action.
- Confirm the UI uses real API data and does not rely on mock document data.
- Confirm type labels can be localized for both `ru` and `en` while preserving stable backend enum values.
