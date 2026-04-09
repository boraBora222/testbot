# Task: Orders Read Flows: List, Detail, Dashboard

- Objective: Replace runtime mock-driven read flows with authenticated backend order data across deals list, deal detail, and dashboard summary surfaces while preserving the existing deal-documents API and explicit failure states.
- Owner: Dev
- Dependencies: `02-order-service-and-ui-mappers.md`, `front/src/pages/dashboard/deals/index.tsx`, `front/src/pages/dashboard/deals/[id].tsx`, `front/src/pages/dashboard/index.tsx`, `front/src/components/dashboard/DealsTable.tsx`, `front/src/config/service.ts`, `web/routers/orders.py`, `web/routers/deals.py`
- Success Criteria:
  - `/dashboard/deals` reads real user data from `GET /orders`.
  - `/dashboard/deals/{id}` loads its primary content from `GET /orders/{order_id}`.
  - `/dashboard` no longer reads `mockDeals` at runtime.
  - Empty, loading, `404`, `409`, and generic failure states are explicit.
  - The detail page keeps documents on the real deal-document API and never substitutes another deal when lookup fails.

## Steps

1. Replace the deals-list data source.
```text
- Remove `mockDeals` from `front/src/pages/dashboard/deals/index.tsx`.
- Load the initial list through `orderService.listOrders(...)`.
- Keep route navigation behavior unchanged so clicking a row still opens `/dashboard/deals/{id}`.
```

2. Align filters and pagination with backend semantics.
```text
- Map the current filter UI to backend-supported values such as `all`, `active`, `new`,
  `waiting_payment`, `processing`, `completed`, and `cancelled`.
- Keep the UI labels if they are still product-appropriate, but make the mapping explicit.
- Decide the first-pass pagination behavior from backend `page`, `page_size`, and `total` values.
```

3. Replace the primary detail data source.
```text
- Remove mock-based deal lookup from `front/src/pages/dashboard/deals/[id].tsx`.
- Load the main card, status, security block, and timeline from `orderService.getOrder(id)`.
- Reuse the mapper from task `02` instead of repeating backend-to-UI conversions inline.
```

4. Preserve and tighten document integration.
```text
- Keep document list and download behavior on the existing deal-document API.
- Ensure the document `dealId` is the same real order id used by the primary detail card.
- Remove any logic that can silently replace the requested deal with a different one.
```

5. Replace dashboard summary and recent deals with live data.
```text
- Remove `mockDeals` usage from `front/src/pages/dashboard/index.tsx`.
- Drive the last-deal and recent-deals sections from authenticated backend `orders`.
- If turnover or other aggregates require a dedicated backend summary endpoint, document that gap
  explicitly instead of simulating completeness from partial data.
```

6. Keep state handling explicit.
```text
- Render clear loading, empty, and error states for list, detail, and dashboard pages.
- Treat missing route params, `404`, `401`, `403/409`, and generic failures as explicit states.
- Do not silently fall back to local mock data when a request fails.
```

## Validation

- Confirm `/dashboard/deals`, `/dashboard/deals/{id}`, and `/dashboard` no longer import runtime `mockDeals`.
- Confirm the detail page never shows another deal when the requested `id` is invalid or inaccessible.
- Confirm document requests remain scoped to the requested real order id.
- Confirm dashboard summaries are clearly grounded in actual backend responses.
