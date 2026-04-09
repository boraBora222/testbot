# Task: Dashboard Summary and Recent Deals

- Objective: Replace runtime mock data on the dashboard with authenticated backend order data for last-deal, recent-deals, and activity surfaces, and document the final strategy for summary aggregation.
- Owner: Dev
- Dependencies: `01-order-service-and-ui-mappers.md`, `02-deals-list-api-integration.md`, `03-deal-detail-and-documents-hardening.md`, `front/src/pages/dashboard/index.tsx`, `web/routers/orders.py`
- Success Criteria:
  - `/dashboard` no longer reads `mockDeals` at runtime.
  - Last deal and recent deals are driven by real backend state.
  - Summary behavior such as total turnover is either implemented honestly or documented as requiring a dedicated backend endpoint.
  - No placeholder aggregate is presented as if it were real data.

## Steps

1. Replace the dashboard mock source.
```text
- Remove `mockDeals` usage from `front/src/pages/dashboard/index.tsx`.
- Load the data needed for last deal, recent deals, and lightweight activity blocks through
  `orderService.listOrders(...)`.
- Reuse the established order-to-deal mapper instead of duplicating transformations.
```

2. Drive the last-deal and recent-deals sections from backend data.
```text
- Use the first or latest backend item as the source for the "last deal" block.
- Use a defined subset of returned items for the recent-deals list.
- Keep empty-state handling explicit when the user has no orders.
```

3. Decide and document the summary strategy.
```text
- If the current frontend only has a paginated orders endpoint, document whether turnover and
  similar metrics are temporarily limited to loaded data or require a backend summary endpoint.
- Prefer explicit product wording over fake completeness.
- If a dedicated backend endpoint is required, document it as a follow-up rather than simulating it.
```

4. Keep greeting and account-state behavior intact.
```text
- Continue using the authenticated user context for display name and verification state.
- Keep the dashboard resilient when a user is authenticated but has zero orders.
- Avoid mixing user-profile concerns with order-summary concerns in the same data layer.
```

## Validation

- Confirm the dashboard no longer imports runtime mock deals.
- Confirm the dashboard remains usable for users with no orders yet.
- Confirm all displayed order-derived metrics are clearly grounded in actual backend responses.
