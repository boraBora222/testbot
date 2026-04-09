# Task: New Deal Draft, Submit, and Resume

- Objective: Convert the local-only new-deal wizard into a real backend-backed draft and submit flow so success is shown only after a real order is created and in-progress work can be resumed safely.
- Owner: Dev
- Dependencies: `02-order-service-and-ui-mappers.md`, `03-orders-read-flows-list-detail-dashboard.md`, `front/src/pages/dashboard/new-deal/index.tsx`, `web/routers/orders.py`, `web/models.py`, `shared/types/enums.py`
- Success Criteria:
  - `/dashboard/new-deal` restores an existing draft when one exists.
  - Wizard progress is persisted through the backend draft API.
  - Final submission uses the backend submit endpoint and returns a real `order_id`.
  - The current fake success path is removed.
  - Draft restore and submit failures are explicit.

## Steps

1. Define the frontend-to-backend field mapping.
```text
- Document how the current UI fields map to backend `exchange_type`, `from_currency`,
  `to_currency`, `amount`, `network`, `address`, and `use_whitelist`.
- Keep the mapping explicit for the current `buy` and `sell` UX.
- Do not invent missing currency or direction defaults inside business logic.
```

2. Restore an existing draft on page load.
```text
- Attempt `GET /order-drafts/current` when the page opens.
- If a draft exists, hydrate the wizard state from it.
- If the backend returns `404`, treat that as "no current draft" rather than an unexpected error.
```

3. Persist wizard progress explicitly.
```text
- Save progress through `PUT /order-drafts/current` on step transitions or explicit checkpoints.
- Align saved `current_step` with backend values: `amount`, `address`, and `confirm`.
- Keep validation strict so invalid data does not advance into a confirm-step draft.
```

4. Submit the draft through the backend.
```text
- Replace the local completion branch with `POST /order-drafts/current/submit`.
- Show success only after a successful backend response.
- Render the real `order_id` in the confirmation state instead of a hardcoded placeholder value.
```

5. Handle draft and submit failures explicitly.
```text
- Show clear UI for `404` draft-missing, `409` business-rule failures, `422` validation errors,
  and generic request failures.
- Keep request failure logging contextual.
- Do not fall back to a local success state when submit fails.
```

## Validation

- Confirm a page refresh can restore an existing backend draft.
- Confirm the final success state is impossible without a real backend submit response.
- Confirm the wizard remains aligned with backend draft semantics rather than the old mock flow.

## Current Implementation Status

Implemented in the current repo:

- `/dashboard/new-deal` restores the active draft through `GET /order-drafts/current`.
- Step transitions persist through `PUT /order-drafts/current`.
- Final confirmation submits through `POST /order-drafts/current/submit` and shows success only after a real backend response with a real `order_id`.
- Repeat flow prefill is supported through session handoff and backend-aligned draft shaping.
- Explicit draft discard/reset is implemented through `DELETE /order-drafts/current` with a dedicated confirmation UI instead of implicit local reset.

Current validation assets:

- Frontend regression coverage exists in `front/src/pages/dashboard/new-deal/__tests__/NewDealPage.test.tsx`.
- Backend contract coverage exists in `tests/test_orders_api.py` for draft upsert, submit, validation, and repeat edge cases.

Remaining gap:

- The flow is implemented and tested, but final release notes should still call out any future backend aggregate/read-model follow-ups separately instead of mixing them into the draft contract.
