# Task: Domain Model and Storage Foundation

- Objective: Establish the shared document data model, enum contracts, storage fields, and repository rules required for both profile documents and deal documents.
- Owner: Dev
- Dependencies: [Documents and compliance specification](../../specifications/documents_and_compliance), existing `MaterialDB`, current material persistence layer, and current deal-card document placeholder flow
- Success Criteria:
  - `MaterialContentType` supports `CLIENT_DOC` and `DEAL_DOC`.
  - Client and deal document types are defined as explicit enums with no speculative extra states.
  - `MaterialDB` has a documented destination for `deal_id`, file metadata, Telegram source metadata, and `s3_key`.
  - The one-active-document-per-`client_doc_type` rule is documented for each `user_id`.
  - Index expectations exist for `user_id`, `content_type`, `deal_id`, and `created_at`.

## Steps

1. Extend the shared material content model.
```text
- Add `CLIENT_DOC` and `DEAL_DOC` to the material content-type contract.
- Preserve the existing material contour instead of introducing a new document subsystem.
- Keep the document distinction explicit so downstream code does not infer behavior from ad hoc flags.
```

2. Define document type enums.
```text
- Add the client-document enum values required by the specification:
  `inn`, `ogrn`, `charter`, `protocol`, `director_passport`,
  `egrul_extract`, `bank_details`, and `other`.
- Add the deal-document enum values required by the specification:
  `contract`, `act`, `confirmation`, and `other`.
- Keep enum values stable because web, bot, and API responses will depend on them.
```

3. Extend the document record fields.
```text
- Document the required fields for one shared material record:
  `id`, `user_id`, `content_type`, `client_doc_type`, `deal_doc_type`,
  `deal_id`, `file_name`, `mime_type`, `file_size`, `telegram_file_id`,
  `s3_key`, `created_at`, and `updated_at`.
- Make `deal_id` mandatory for `DEAL_DOC` and empty for `CLIENT_DOC`.
- Keep file metadata explicit so profile and deal lists can render without storage lookups.
```

4. Define replacement and uniqueness rules.
```text
- Enforce one active client document per `user_id + client_doc_type`.
- Treat re-upload of the same client document type as a replacement of the previous file,
  not as a new versioned record.
- Do not store `s3_url` in the database; generate download links dynamically.
```

5. Define repository and index expectations.
```text
- Add or document repository methods for:
  profile document list/create/delete/download lookup,
  deal document list/create/download lookup,
  and replacement-aware writes for client documents.
- Add indexes for `user_id`, `content_type`, `deal_id`, and `created_at`.
- Keep repository rules fail-fast when record state is invalid or incomplete.
```

## Validation

- Review sections `3`, `6`, `7`, and `9.1` of the specification and confirm every required field has a clear storage destination.
- Confirm the model keeps one shared `MaterialDB`-based contour for both profile and deal documents.
- Confirm the replacement rule is explicit for `client_doc_type` and does not introduce hidden history behavior.
