# Task: Tests, Rollout, and Release Readiness

- Objective: Lock the exchange rollout with focused regression coverage, backend contract and smoke validation, runtime mock cleanup, and one final release-readiness checklist.
- Owner: Dev
- Dependencies: `02-order-service-and-ui-mappers.md`, `03-orders-read-flows-list-detail-dashboard.md`, `04-new-deal-draft-submit-and-resume.md`, `05-observability-async-and-supporting-read-models.md`, `06-security-data-and-audit-hardening.md`, `docs/specifications/playwrighttest.md`, `.github/workflows/backend-tests.yml`
- Success Criteria:
  - Focused frontend regression tests cover the highest-risk read and write flows.
  - Exchange backend contract checks cover the main order, draft, profile, and document surfaces.
  - Runtime dashboard and deals pages no longer depend on mock data.
  - The rollout has one explicit final validation checklist with honest notes about remaining backend gaps.

## Steps

1. Add focused frontend regression tests.
```text
- Cover deals list rendering from real API responses.
- Cover deal detail not-found or error behavior so the page cannot fall back to another deal.
- Cover new-deal submit behavior so success appears only after a successful backend response.
- Cover dashboard rendering from real order data, including an empty-orders state.
```

2. Add exchange contract and smoke validation.
```text
- Add backend contract tests for `orders`, `order-drafts`, profile or whitelist-related surfaces,
  and document flows that are part of the exchange path.
- Add or document a smoke scenario such as `register -> verify -> login -> create draft -> submit -> list orders`.
- Add or document the storage-related scenario `upload document -> presigned download`.
```

3. Clean up runtime mock dependencies.
```text
- Remove runtime imports of `mockDeals` from dashboard and deals pages.
- If static UI config such as network options still belongs on the frontend, move it to a neutral
  non-mock config location.
- Keep test fixtures and MSW data separate from runtime production code.
```

4. Recheck state and contract consistency.
```text
- Confirm every runtime consumer reads backend order data through the shared service layer.
- Confirm no page reintroduces hidden fallbacks for required order fields.
- Confirm backend `orders` remain the source of truth and frontend `Deal` remains a presentation model.
```

5. Finish release-readiness notes.
```text
- Capture final validation steps for linting, tests, rollout checks, and known limitations.
- Record backend gaps explicitly, especially when dashboard aggregates or supporting read models still
  need follow-up endpoints.
- Keep the sign-off document honest rather than masking missing behavior behind placeholders.
```

## Validation

- Confirm the most product-critical exchange regressions are covered by automated checks.
- Confirm no runtime authenticated page in this scope still depends on `dashboardMocks.ts`.
- Confirm the final rollout notes describe limitations explicitly instead of implying complete coverage where none exists.

## Current Coverage Snapshot

Already implemented:

- Frontend dashboard/orders regression suite is wired through `front/package.json` as `npm run test:dashboard-orders`.
- Docker test services exist for:
  - `front-test`
  - `front-dashboard-orders-test`
  - `front-smoke`
  - `backend-test`
- Frontend CI already runs auth, dashboard/orders, and smoke checks in `.github/workflows/front-auth-tests.yml`.
- Backend contract tests now cover:
  - auth storage and auth router checks
  - orders and draft API behavior
  - order lifecycle mapping/helpers
  - profile limits/notifications/whitelist/documents API
  - deal document API
  - whitelist moderation and admin audit flows

## Current Remaining Gaps

- There is still no single automated backend smoke scenario that runs the full path `register -> verify -> login -> create draft -> submit -> list orders` end to end.
- Supporting read-model surfaces such as timeline aggregate views, compliance readiness aggregate views, and persisted notification inboxes remain follow-up work, not rollout blockers for the current live exchange path.
- Release notes should still explicitly state which backend aggregates are intentionally limited by the current API instead of implying a richer read model than the backend actually provides.

## Release-Readiness Rule

- Treat the current dashboard/orders rollout as protected for its primary live flows.
- Treat supporting read models and richer operational dashboards as follow-up scope until dedicated backend contracts exist.
