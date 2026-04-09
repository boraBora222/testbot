# Task: Deals List API Integration

- Objective: Replace the runtime mock deal list with the authenticated backend orders list while keeping the table UI mapper-driven and explicit about loading, empty, and failure states.
- Owner: Dev
- Dependencies: `01-order-service-and-ui-mappers.md`, `front/src/pages/dashboard/deals/index.tsx`, `front/src/components/dashboard/DealsTable.tsx`, `web/routers/orders.py`
- Success Criteria:
  - `/dashboard/deals` reads real user data from `GET /orders`.
  - Status filters are translated to backend-supported query values instead of local mock-only states.
  - The list page no longer depends on `mockDeals` at runtime.
  - Empty, loading, and error states are explicit.

## Steps

1. Replace the page-level data source.
```text
- Remove `mockDeals` from `front/src/pages/dashboard/deals/index.tsx`.
- Load the initial list through `orderService.listOrders(...)`.
- Keep route navigation behavior unchanged so clicking a row still opens `/dashboard/deals/{id}`.
```

2. Align filters with backend list semantics.
```text
- Backend supports list filters such as `all`, `active`, `new`, `waiting_payment`, `processing`,
  `completed`, and `cancelled`.
- Document how the current UI filter set maps to those values.
- If the current filter labels are simplified, keep the simplification in the UI but make the
  mapping explicit in code and docs.
```

3. Decide the first-pass pagination contract.
```text
- `GET /orders` is paginated with `page` and `page_size`.
- Either implement visible pagination now or document the initial page-size strategy used for the
  first rollout.
- Do not fake totals from the current page length if the backend already returns `total`.
```

4. Keep `DealsTable` presentation-only.
```text
- Feed `DealsTable` already-mapped `Deal[]` data.
- Avoid teaching the table about backend field names such as `order_id` or `status_meta`.
- If the table needs new columns later, extend the mapper and props deliberately.
```

5. Add explicit state handling.
```text
- Render a loading state while the list is in flight.
- Render a clear empty state when the backend returns no items.
- Render a clear error state for `401`, `409`, and generic request failures.
- Do not silently fall back to local mock data when the request fails.
```

## Validation

- Confirm `/dashboard/deals` still navigates correctly to the detail page.
- Confirm the reported totals and list counts come from backend responses, not mock array lengths.
- Confirm runtime list rendering behaves correctly for empty, filtered, and error responses.
