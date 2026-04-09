# Dashboard Orders Rollout Status

This document is the execution-facing version of the unified dashboard orders rollout plan. It does not replace the original planning artifact, but it captures the current implementation state, the remaining work, and the next safe delivery steps.

## Goal

Complete the dashboard orders rollout by aligning frontend dashboard/deals/new-deal flows with the existing backend `orders` and `order-drafts` APIs, while keeping explicit error handling, preserving backend contracts, and avoiding silent fallback behavior.

## Current Status Snapshot

### Completed

- Phase 0: rollout gates and runtime feature flags are in place.
- Phase 1: frontend service foundation, mapper layer, and typed contracts are in place.
- Phase 3: live read flows for deals list, deal detail, and dashboard summary are wired to the live orders API.
- Phase 4: new-deal draft restore, submit, repeat prefill, and explicit draft discard/reset are wired to the live draft/order APIs.

### In Progress

- Phase 5: observability and async hardening are implemented for current exchange producers/consumers, while supporting read models remain documentation-only follow-up work.
- Phase 6: audit hardening is implemented for whitelist moderation and queued order-status transitions, but broader operational audit/read-model work is still bounded follow-up scope.
- Phase 7: automated verification is in place for frontend live flows and backend exchange contracts, but one full backend smoke scenario is still not automated end to end.

### Not Started

- No additional rollout phase is fully unstarted inside the current dashboard/orders scope.

## What Has Already Been Implemented

### 1. Rollout gates and feature flags

Implemented:

- Runtime feature flags for dashboard live orders and dashboard draft flows in `front/src/config/runtimeFeatures.ts`.
- Existing backend identity gate continues to rely on `linked_exchange_user_id`; frontend live flows now surface the backend `409` state instead of silently falling back.

Impact:

- Rollout can be enabled or disabled without introducing alternate business logic paths inside page components.

### 2. Frontend service foundation and typed contract layer

Implemented:

- Expanded dashboard-related frontend types in `front/src/types/index.ts`.
- Added a dedicated order contract and mapping layer in `front/src/lib/orders.ts`.
- Added `orderService` to `front/src/config/service.ts` covering:
  - `GET /orders`
  - `GET /orders/{order_id}`
  - `POST /orders/{order_id}/repeat`
  - `GET /order-drafts/current`
  - `PUT /order-drafts/current`
  - `DELETE /order-drafts/current`
  - `POST /order-drafts/current/submit`
- Added neutral exchange UI config in `front/src/config/exchangeOptions.ts`.

Impact:

- Frontend pages now have one typed, authenticated source for orders and drafts.
- Backend payloads are mapped explicitly into the presentation-oriented `Deal` model.

### 3. Backend lifecycle hardening

Implemented:

- `UpsertOrderDraftRequest` in `web/models.py` now validates required fields per draft step instead of forcing one full payload shape for every save.
- `POST /orders/{order_id}/repeat` in `web/routers/orders.py` now converts non-repeatable business errors into explicit `409` responses.
- `POST /order-drafts/current/submit` now logs validation and business-rule failures with context before re-raising as HTTP errors.

Impact:

- Draft saves are more compatible with step-based UI progression.
- Repeat and submit errors are now explicit and observable.

### 4. Live read flows

Implemented:

- `front/src/pages/dashboard/deals/index.tsx` now loads deals through `orderService.listOrders(...)` and surfaces loading, empty, `401`, `409`, and generic error states.
- `front/src/pages/dashboard/deals/[id].tsx` now loads the main deal card through `orderService.getOrder(...)`, keeps documents on the real deal documents API, and removes the old `mockDeals.find(...) || mockDeals[0]` substitution pattern.
- `front/src/pages/dashboard/index.tsx` now reads recent deals and the last deal from live orders when the feature flag is enabled.

Impact:

- The highest-risk read surfaces now have a live data path.
- The deal detail page no longer substitutes another deal when the requested id is missing.

### 5. New-deal live draft flow

Implemented:

- Added shared new-deal helpers in `front/src/lib/newDeal.ts`.
- `front/src/pages/dashboard/new-deal/index.tsx` now:
  - attempts to restore the current backend draft,
  - saves draft progress on step transitions,
  - submits through `POST /order-drafts/current/submit`,
  - shows success only after a real backend response,
  - supports repeat prefill handoff through session storage,
  - supports explicit discard/reset through `DELETE /order-drafts/current`.

Impact:

- The old local-only success path has been removed from the main dashboard deal-creation flow.
- The dashboard write flow no longer relies on implicit local reset behavior when a user wants to discard a draft.

### 6. Runtime mock cleanup and frontend verification

Implemented:

- Public calculator config was moved out of `dashboardMocks.ts` into `front/src/config/exchangeOptions.ts`.
- `front/src/components/blocks/CalculatorWizard.tsx` now reads neutral exchange UI config instead of using dashboard mock config values.
- `front/src/config/dashboardMocks.ts` was updated to remain compatible as a fallback fixture source.
- Focused frontend regression tests now exist for:
  - dashboard summary,
  - deals list,
  - deal detail,
  - new-deal draft/submit flow,
  - order service and mapper behavior.
- Docker test services and frontend CI now run both auth tests and dashboard/orders tests.

Impact:

- The dashboard mock bundle is no longer acting as a shared config source for unrelated runtime code.
- The highest-risk authenticated dashboard flows are protected by automated frontend checks instead of relying only on manual verification.

### 7. Observability and queue envelope hardening

Implemented:

- `web/main.py` now keeps one canonical `correlation_id` through request handling and mirrors it into `X-Request-Id`.
- Current async producers publish a soft-versioned `v1` envelope with `version + meta + payload`.
- Compatibility mirrors remain in place at the root payload level during transition so legacy queue readers are not broken.
- `bot/queue_consumer.py` now normalizes both legacy and `v1` queue messages before processing.

Impact:

- Logs can correlate request, enqueue, dequeue, and Telegram send stages by one `correlation_id`.
- Queue contract rollout is additive rather than a hidden breaking change.

### 8. Audit hardening

Implemented:

- Whitelist moderation already writes append-only audit entries.
- Critical order status transitions coming from the order-status queue now write append-only audit entries with:
  - `old_status`
  - `new_status`
  - `source`
  - `actor`
  - `reason`
  - `correlation_id`
  - queue context

Impact:

- Critical exchange status changes are no longer observable only through logs; they now have a durable audit trail.

## Remaining Work

### Phase 2. Backend/package hardening

Still needed:

- Review whether additional lifecycle entry points or facades are needed to reduce ad-hoc usage patterns in future bot/web work.
- Verify index coverage for:
  - `orders(user_id, created_at)`
  - `orders(user_id, status, created_at)`
  - unique active draft on `(owner_channel, owner_id)`
- Decide whether any TTL cleanup policy should be documented or implemented for MVP drafts.

### Phase 4. Live write flow completion

Still needed:

- Verify all repeat entry points that should be supported for MVP.
- Recheck step transitions and edge-case handling for `409` and `422` responses against the final UI behavior.

### Phase 5. Runtime cleanup and docs

Still needed:

- Remove remaining runtime fallback dependencies on `mockDeals` from authenticated dashboard pages when live orders are considered stable enough to stop using the fallback path.
- Document:
  - which runtime flags control the rollout,
  - what known backend gaps remain,
  - which aggregate values are intentionally limited by the current backend API.
- Keep supporting read-model follow-up honest: timeline aggregate surfaces, compliance-readiness summaries, and notification inboxes are still follow-up work.

### Phase 6. Tests, Docker, and CI

Still needed:

- Backend tests:
  - add one fuller exchange smoke scenario spanning auth -> draft -> submit -> list.
- Rollout notes:
  - keep the final release checklist honest about which read models are still not backed by dedicated backend endpoints.

## Updated Execution Order

1. Finish backend lifecycle hardening and verify the remaining draft/repeat contract edges.
2. Remove remaining authenticated runtime fallback usage of dashboard mocks when rollout flags no longer need compatibility fixtures.
3. Add one fuller backend smoke scenario for exchange signup/login/draft/submit/list flow.
4. Keep rollout notes updated as supporting read-model follow-ups are clarified.

## File-Level Progress Reference

Primary implementation files already touched:

- `front/src/config/runtimeFeatures.ts`
- `front/src/config/exchangeOptions.ts`
- `front/src/types/index.ts`
- `front/src/lib/orders.ts`
- `front/src/lib/newDeal.ts`
- `front/src/config/service.ts`
- `front/src/pages/dashboard/deals/index.tsx`
- `front/src/pages/dashboard/deals/[id].tsx`
- `front/src/pages/dashboard/index.tsx`
- `front/src/pages/dashboard/new-deal/index.tsx`
- `front/src/components/dashboard/DealsTable.tsx`
- `front/src/components/dashboard/StatusBadge.tsx`
- `front/src/components/blocks/CalculatorWizard.tsx`
- `front/src/config/dashboardMocks.ts`
- `web/models.py`
- `web/routers/orders.py`

## Delivery Note

At this checkpoint, the rollout foundation, live read path, live draft/submit path, queue observability contract, and primary automated checks are all in place. The remaining work is mostly cleanup and honesty work: remove final mock-era compatibility paths when safe, add a fuller backend smoke scenario, and keep supporting read-model gaps explicit instead of implying they are already shipped.
