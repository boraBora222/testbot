# Task: Tests, Cleanup, and Release Readiness

- Objective: Lock the new integration behavior with focused regression checks, remove obsolete runtime mock dependencies, and capture the final release-readiness checks for the dashboard and deals rollout.
- Owner: Dev
- Dependencies: `01-order-service-and-ui-mappers.md`, `02-deals-list-api-integration.md`, `03-deal-detail-and-documents-hardening.md`, `04-new-deal-draft-and-submit-flow.md`, `05-dashboard-summary-and-recent-deals.md`
- Success Criteria:
  - Focused frontend regression tests cover the highest-risk read and write flows.
  - Runtime dashboard/deals pages no longer depend on mock data.
  - Static config that remains intentionally local is separated from obsolete mock bundles.
  - The rollout has an explicit final validation checklist.

## Steps

1. Add focused frontend regression tests.
```text
- Cover deals list rendering from real API responses.
- Cover deal detail not-found or error behavior so the page cannot fall back to another deal.
- Cover new-deal submit behavior so success appears only after a successful backend response.
- Cover dashboard rendering from real order data, including an empty-orders state.
```

2. Clean up runtime mock dependencies.
```text
- Remove runtime imports of `mockDeals` from dashboard and deals pages.
- If `networkOptions` remain valid static UI config, move them to a neutral non-mock config file.
- Keep test fixtures and MSW data separate from runtime production code.
```

3. Recheck state and contract consistency.
```text
- Confirm every runtime consumer reads backend order data through the shared service layer.
- Confirm no page reintroduces hidden fallbacks for required order fields.
- Confirm backend `orders` remain the source of truth and frontend `Deal` remains a presentation model.
```

4. Run final quality checks.
```text
- Validate changed frontend files for linter issues.
- Run the targeted frontend test set that covers the migrated pages and services.
- Record any remaining backend gap explicitly, especially if dashboard summary aggregation still
  needs a dedicated endpoint.
```

## Validation

- Confirm the most product-critical regressions are covered by automated checks.
- Confirm no runtime authenticated page in this scope still depends on `dashboardMocks.ts`.
- Confirm final rollout notes describe any known limitations honestly rather than masking them.
