# Task: Deal Detail and Documents Hardening

- Objective: Replace the mock-based deal detail card with real backend order data and harden the page so it never substitutes fake content while still using the existing deal-document API for attachments.
- Owner: Dev
- Dependencies: `01-order-service-and-ui-mappers.md`, `front/src/pages/dashboard/deals/[id].tsx`, `front/src/config/service.ts`, `web/routers/orders.py`, `web/routers/deals.py`
- Success Criteria:
  - `/dashboard/deals/{id}` loads its primary deal content from `GET /orders/{order_id}`.
  - The page keeps documents on the real deal-document API.
  - The fallback `mockDeals.find(...) || mockDeals[0]` is removed.
  - Lookup and access errors are explicit rather than being masked with substitute data.

## Steps

1. Replace the primary detail data source.
```text
- Remove mock-based deal lookup from `front/src/pages/dashboard/deals/[id].tsx`.
- Load the main card, status, security block, and timeline from `orderService.getOrder(id)`.
- Use the mapper layer from task `01` instead of repeating backend-to-UI conversions inline.
```

2. Preserve and tighten document integration.
```text
- Keep document list and download behavior on `dealService.listDocuments(dealId)` and
  `dealService.getDocumentDownloadLink(dealId, documentId)`.
- Ensure the `dealId` used for documents is the same real order id used by the primary card.
- If document upload becomes visible in this page later, align it with the existing backend
  `POST /api/deals/{deal_id}/documents` contract.
```

3. Remove dangerous fallback behavior.
```text
- Delete the fallback that substitutes `mockDeals[0]` when the requested id is not found.
- Treat missing route params, `404`, and `403/409` responses as explicit page states.
- Never render another deal's content as a substitute for the requested one.
```

4. Render backend-native status and timeline data.
```text
- Use backend `timeline` items as the source of truth for progression.
- Use backend `status` and `status_meta` for labels where the UI supports them.
- Document any temporary status-label mapping that is needed for the existing badge components.
```

5. Keep error handling and observability explicit.
```text
- Preserve contextual handling for known API errors such as `401`, `404`, `409`, and `503`.
- Keep request failure logging structured and avoid silent degradation.
- Re-raise unexpected failures instead of swallowing them behind placeholders.
```

## Validation

- Confirm the page never shows another deal when the requested `id` is invalid or inaccessible.
- Confirm document requests remain scoped to the requested deal id.
- Confirm the timeline and status blocks no longer depend on `mockDeals`.
