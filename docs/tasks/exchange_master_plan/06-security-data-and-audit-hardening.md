# Task: Security, Data, and Audit Hardening

- Objective: Strengthen the exchange path with explicit security checks, index review, and audit coverage so the live product flow is safer to operate without changing public contracts or inventing hidden behavior.
- Owner: Dev
- Dependencies: `05-observability-async-and-supporting-read-models.md`, `docs/tasks/TZ.md`, `web/`, `shared/`, `.env`
- Success Criteria:
  - Upload, auth-adjacent, and public-facing paths have documented strict server-side validation.
  - Critical exchange collections have an explicit index review and migration path.
  - Critical status transitions and moderation decisions have documented audit-write coverage.
  - Moderator-facing operational boundaries are documented without renaming existing configuration variables.

## Steps

1. Tighten server-side validation rules.
```text
- Document strict validation for MIME type, file extension, and file size on upload-related flows.
- Document rate-limiting expectations for auth and public-facing forms where appropriate.
- Keep invalid input behavior explicit and fail-fast instead of accepting partial or downgraded processing.
```

2. Review storage and query safety.
```text
- Review index expectations for `orders`, `order_drafts`, `whitelist_addresses`,
  `support_messages`, and session-heavy collections.
- Treat index changes as explicit infrastructure work rather than incidental side effects.
- Keep schema and API compatibility intact while documenting migration expectations clearly.
```

3. Add audit coverage for critical decisions.
```text
- Document audit writes for critical order-status transitions and whitelist moderation outcomes.
- Prefer append-only or side-collection audit records rather than mutating history in place.
- Keep audit scope focused on high-value events for the first rollout.
```

4. Document surface separation and operational boundaries.
```text
- Define the expected separation between client-facing and moderator-facing surfaces.
- Keep any proxy, network, or internal-route restrictions explicit in documentation.
- Preserve existing environment variable names and deployment assumptions where possible.
```

5. Keep rollback and scope realistic.
```text
- Introduce hardening measures in bounded, reversible steps.
- If a control is not ready for rollout, document it as pending instead of presenting it as already guaranteed.
- Do not introduce hidden retries, silent error downgrades, or fake success wording in hardening-related flows.
```

## Validation

- Confirm the hardening task documents concrete controls rather than general security intent.
- Confirm index and audit work are described as explicit operational changes with known scope.
- Confirm existing configuration naming is preserved unless a change is explicitly unavoidable.
