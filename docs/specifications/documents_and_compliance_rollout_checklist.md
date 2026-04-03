# Documents And Compliance Rollout Checklist

This document turns sections `12` and `13` of `docs/specifications/documents_and_compliance` into a release-facing checklist and maps the verification back to sections `5`, `11`, `12`, `13`, and `14` of the specification.

## Audit Verification Matrix

| Scenario | Expected Result | Coverage |
| --- | --- | --- |
| Profile document upload | Upload writes one audit event with user, document type, document id, and storage key context | Automated |
| Same-type profile document replacement | Replacement is audited explicitly as `replace` rather than a silent second upload | Automated |
| Profile document delete | Delete writes one success audit event with document scope and storage key context | Automated |
| Profile or deal document download | Successful temporary-link issuance writes one audit event for the requested document | Automated |
| Deal document attachment | Linking a ready file to a deal writes one `deal_link` audit event with `deal_id` and document type | Automated |
| Unauthorized access attempt | Foreign profile-document or deal-document access writes a denied audit event with actor and scope context | Automated |
| Storage or missing-file failure | Failed download preparation writes an audit event that distinguishes missing stored objects from storage lookup failures | Automated |

## Functional Acceptance Matrix

| Scenario | Expected Result | Coverage |
| --- | --- | --- |
| Telegram bot client-document upload | User can upload a supported file through the bot and receives a clear confirmation | Automated + Manual |
| Web client-document upload | `POST /api/profile/documents` saves the file and returns the metadata contract used by the dashboard | Automated |
| S3/MinIO-backed persistence and profile list rendering | Files are stored by `s3_key`, and the profile list renders metadata without exposing storage internals | Automated + Manual |
| Same-type replacement | Re-uploading the same `client_doc_type` replaces the previous stored document instead of creating version history | Automated |
| Deal card document loading | The deal details page loads document rows through the live deal-documents API instead of mock document rows | Automated + Manual |
| Temporary-link download flow | Profile and deal downloads return `downloadUrl` plus `expiresAt`, not the file body or a permanent URL | Automated |
| Foreign-document denial | Access to another user's profile document or inaccessible deal document is rejected with `403` | Automated |

## Non-Functional Verification Matrix

| Check | Expected Result | Coverage |
| --- | --- | --- |
| Supported format enforcement | Only PDF, DOC, DOCX, XLS, XLSX, JPG, and PNG are accepted for profile and deal uploads | Automated |
| Size limit enforcement | Files larger than `10 MB` are rejected for both profile and deal uploads | Automated |
| Presigned URL TTL | Temporary download links are issued with `15 minutes` TTL (`900` seconds) | Automated |
| Storage source of truth | Downloads are served through S3/MinIO-backed presigned URLs, not Telegram file links | Automated + Review |
| No public permanent links | Stored records and API responses do not expose `s3_url`, permanent public links, or raw storage credentials | Automated + Review |
| Clear failure messaging | Telegram-transfer errors, storage upload errors, storage lookup errors, and missing-file cases produce clear user-facing errors | Automated |

## MVP Scope Guards

- No moderation flow is added in this release.
- No PDF generation or template generation is introduced.
- No lifecycle statuses such as `approved`, `rejected`, `signed`, or `archived` are introduced for documents.
- No EDI integration is introduced.
- No document versioning is introduced beyond same-type replacement.
- No separate `company` entity is introduced; document ownership remains `user_id` scoped.
- No hidden fallback download path from Telegram or public permanent object URL is introduced.

## Operational Assumptions

- `DOCUMENT_STORAGE_ENDPOINT`, `DOCUMENT_STORAGE_PUBLIC_ENDPOINT`, `DOCUMENT_STORAGE_BUCKET`, `DOCUMENT_STORAGE_ACCESS_KEY`, `DOCUMENT_STORAGE_SECRET_KEY`, and `DOCUMENT_STORAGE_REGION` are configured for the target environment.
- The document bucket remains private, and browser downloads are performed only through presigned URLs.
- The backend can reach the private S3/MinIO endpoint for upload, delete, and existence checks.
- The browser-facing public endpoint resolves correctly from the deployed dashboard and bot-linked clients.
- The configured presign TTL remains `900` seconds unless the specification is updated deliberately.
- Deployment notes record any bucket-policy, DNS, TLS, or MinIO-specific assumptions required for rollout.

## Suggested Release Checks

1. Run the backend document suites covering foundations, profile API, deal API, and Telegram bot upload flows.
2. Manually upload one client document through Telegram bot and one through the dashboard, then verify both appear in the profile list.
3. Re-upload the same profile document type and confirm the old file is replaced without a new logical document version.
4. Open a deal card, confirm the documents block loads from the live API, and verify a deal download opens a temporary link.
5. Confirm foreign profile-document and foreign-deal access attempts are rejected and leave auditable traces.
6. Record deployment-specific storage observations before sign-off, especially bucket privacy, endpoint reachability, and presigned-link behavior.

## Release Sign-Off

The release can be signed off only when all items below are true:

1. Audit coverage from section `5` is present for upload, replace, delete, download, and deal-link actions.
2. Acceptance scenarios from section `12` are covered by explicit automated or manual checks.
3. Error and limit cases from section `11` are verified alongside happy-path usage.
4. Rollout still respects implementation order and MVP boundaries from section `13` and excluded scope from section `14`.
5. Backend, storage, Telegram bot, web dashboard, and release stakeholders share one final checklist for release readiness.
