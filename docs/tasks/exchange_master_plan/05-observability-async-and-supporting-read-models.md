# Task: Observability, Async, and Supporting Read Models

- Objective: Standardize correlation, logging, and async message contracts around the live exchange flows so failures are observable, new queue consumers are version-safe, and follow-up read models have an explicit foundation.
- Owner: Dev
- Dependencies: `03-orders-read-flows-list-detail-dashboard.md`, `04-new-deal-draft-submit-and-resume.md`, `docs/tasks/TZ.md`, `web/`, `bot/`, `shared/`
- Success Criteria:
  - HTTP, bot, and Redis-backed exchange flows have one documented `correlation_id` strategy.
  - New async producers and consumers use a soft-versioned queue envelope contract.
  - Failure logging is contextual and explicit rather than silent or downgraded.
  - Follow-up read-model opportunities are documented honestly instead of being implied by placeholders.

## Steps

1. Define one correlation strategy.
```text
- Document how `correlation_id` is generated, propagated, and logged across HTTP requests,
  bot commands, and Redis messages.
- Keep the strategy additive so existing consumers are not broken.
- Treat missing correlation context as an implementation error, not a silent best-effort detail.
```

2. Standardize the async message envelope for new work.
```text
- Define a versioned message envelope for new queue publications.
- Keep the rollout soft: new consumers should understand the new contract, while legacy paths can
  continue to read the existing format during transition.
- Document the minimum required metadata for new messages.
```

3. Make failure handling operationally useful.
```text
- Document structured logging expectations for request failures and message-processing failures.
- Keep known, expected failures explicit and contextual.
- Do not describe hidden retries or silent warning-only behavior for real processing failures.
```

4. Document bounded supporting read models.
```text
- Capture the most natural read-model follow-ups from the exchange flow such as timeline,
  compliance-readiness, and notification-oriented views.
- Keep the first version documentation-only if the backend contract is not ready.
- Do not present these surfaces as complete features if they still require backend follow-up.
```

5. Define rollout boundaries.
```text
- Keep the observability contract non-breaking for existing public APIs.
- Scope new envelope rules to new producers and consumers first.
- If a worker or queue path is still ambiguous, document that gap explicitly rather than guessing.
```

## Validation

- Confirm the documentation defines one end-to-end correlation story instead of separate per-surface conventions.
- Confirm new async behavior is introduced as an additive contract and not as a hidden breaking change.
- Confirm supporting read models are framed as explicit follow-ups when they are not yet backed by stable contracts.

## Current Contract

- HTTP: `X-Correlation-Id` is the canonical request/response header. `X-Request-Id` is kept as a compatibility mirror of the same value.
- Async payloads: `_async_trace.correlation_id` is the canonical field. `_async_trace.trace_id` may remain temporarily, but only as a mirror of `correlation_id`.
- Producers: web producers inherit the active HTTP correlation context automatically; bot-originated async flows generate a correlation id at enqueue time.
- Consumers: bot queue consumers log dequeue and send stages with the same `correlation_id`, so one field links request, enqueue, and consume.

## Current `v1` Queue Envelope

New async producers publish a soft-versioned envelope:

```json
{
  "version": "v1",
  "meta": {
    "correlation_id": "abc123",
    "trace_id": "abc123",
    "published_at": "2026-04-09T10:00:00+00:00",
    "producer": "web.users.broadcast",
    "queue_name": "reply_bot_broadcast_queue",
    "event_name": "broadcast"
  },
  "payload": {
    "type": "broadcast",
    "user_id": 321,
    "text": "Hello"
  }
}
```

Transition rule:

- New consumers should prefer `payload` and `meta` when `version == v1`.
- Legacy mirrors stay in place during rollout: root business fields and `_async_trace` are still present so existing queue handlers are not broken by the envelope addition.
- `trace_id` is compatibility-only and must mirror `correlation_id`; new code should not invent a separate tracing field.

## Current Implementation Scope

- `web/main.py` binds one `correlation_id` per request and mirrors it into `X-Request-Id`.
- `web/routers/users.py`, `web/services/application_service.py`, `bot/handlers/common.py`, `bot/crypto_exchange_bot.py`, and `scripts/test_redis_events.py` now publish `v1` envelopes.
- `bot/queue_consumer.py` understands both legacy payloads and `v1` envelopes by normalizing messages before processing.
- Order-status queue transitions now write append-only audit records with `source`, `actor`, `reason`, `correlation_id`, `queue_name`, and `event_name`.

## Supporting Read-Model Follow-Up

The most natural next read-model surfaces are still documentation-only follow-ups:

- Timeline read model:
  current order detail responses already expose per-order timeline shaping, but there is no standalone timeline feed or manager-oriented aggregate endpoint yet.
- Compliance readiness read model:
  the UI can assemble partial state from profile limits, whitelist entries, and profile documents, but there is no single backend contract that answers “is this account ready to trade?” in one call.
- Notification/inbox read model:
  Redis queue tracing exists for delivery diagnostics, but there is no persisted event inbox or notification-center API for end users or managers.

Backend gap rule:

- Until dedicated endpoints or persisted projections exist, these surfaces should be described as follow-up read models rather than treated as already-live product capabilities.
