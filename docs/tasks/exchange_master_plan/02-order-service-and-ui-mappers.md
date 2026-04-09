# Task: Order Service and UI Mappers

- Objective: Add a single frontend order service and explicit UI mapping layer so dashboard and deal pages can consume backend `orders` and `order-drafts` contracts without leaking backend field names or mock-era assumptions across the UI.
- Owner: Dev
- Dependencies: `01-domain-boundaries-and-service-facades.md`, `front/src/config/service.ts`, `front/src/types/index.ts`, `web/routers/orders.py`, `web/models.py`, `shared/types/enums.py`
- Success Criteria:
  - `orderService` exists in `front/src/config/service.ts` and reuses the existing authenticated request path.
  - Frontend API types cover `OrderResponse`, `OrderListResponse`, and current draft payloads.
  - One explicit mapper converts backend `OrderResponse` values into the presentation-oriented `Deal` model.
  - Backend `timeline`, `status_meta`, and draft-step contracts are handled explicitly without hidden fallback defaults.

## Steps

1. Define the frontend API contract for orders and drafts.
```text
- Mirror the backend shapes from `web/models.py` for `OrderResponse`, `OrderListResponse`,
  `CurrentOrderDraftResponse`, and the draft upsert payload.
- Keep required backend fields required on the frontend side.
- Preserve backend field names in the API-layer types instead of renaming them prematurely.
```

2. Extend the authenticated frontend service layer.
```text
- Add `orderService` to `front/src/config/service.ts`.
- Reuse the existing authenticated request helper instead of introducing a second fetch wrapper.
- Cover `GET /orders`, `GET /orders/{order_id}`, `GET /order-drafts/current`,
  `PUT /order-drafts/current`, `DELETE /order-drafts/current`, `POST /order-drafts/current/submit`,
  and `POST /orders/{order_id}/repeat` if the current UI needs repeat behavior.
```

3. Add explicit UI mappers.
```text
- Convert backend `OrderResponse` into the UI `Deal` model used by the dashboard components.
- Map `order_id` to `Deal.id`, backend timestamps to page-friendly date fields, and backend
  `timeline` entries to `DealStep[]`.
- Decide and document how backend statuses like `new` and `waiting_payment` appear in the
  existing dashboard status vocabulary.
```

4. Align draft semantics with backend enums.
```text
- Use backend `ExchangeType` values exactly: `crypto_to_fiat`, `fiat_to_crypto`, and `crypto_to_crypto`.
- Use backend `DraftStep` values exactly: `amount`, `address`, and `confirm`.
- Document how the current two-direction UI (`buy` and `sell`) maps to backend `exchange_type`,
  `from_currency`, and `to_currency` values.
```

5. Keep failure handling explicit.
```text
- Do not invent default values for missing backend data.
- Surface invalid or incomplete payloads as errors rather than masking them in the mapper.
- Keep logging contextual on request failures and preserve re-raise behavior for unexpected errors.
```

## Validation

- Confirm every future dashboard or deals consumer can read data through `orderService` instead of direct page-local fetch logic.
- Confirm the UI mapper is the only place where backend `orders` semantics become frontend `Deal` semantics.
- Confirm the implementation does not introduce chained defaults for required business fields.
