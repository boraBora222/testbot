# Latency And Async Notifications Checklist

This checklist is for practical verification of frontend bundle size, API latency, and async notification delivery in the current repository.

## 1. Frontend chunk check

Run the production build from the frontend workspace:

```powershell
cd front
npm run build
```

What to verify:

- The build output is split into multiple route/vendor chunks instead of a single monolithic `index-*.js`.
- The main entry chunk stays materially smaller than the previous baseline from before the split work.
- Route chunks are created for dashboard/auth/public secondary pages.
- Heavy vendor groups are separated into files like `react-vendor`, `motion-vendor`, `icons-vendor`, or `ui-vendor`.

Good review habit:

- Paste the build output into the PR description and compare it against the last known baseline.
- Treat any new unexpectedly large `index-*.js` or `vendor-*.js` as a regression signal.

## 2. API latency instrumentation

The FastAPI app now adds these headers to API responses:

- `X-Correlation-Id`
- `X-Request-Id`
- `Server-Timing: app;dur=<ms>`

The frontend fetch wrapper can also log client-side timing in the browser console.

Enable it in the frontend env:

```powershell
$env:VITE_ENABLE_REQUEST_TIMING="1"
```

Then start the frontend and watch the browser console for entries like:

```text
[api-latency] { path, status, clientDurationMs, correlationId, serverTiming }
```

What to verify:

- `clientDurationMs` is reasonable for local flows.
- `correlationId` is present, so browser observations can be correlated with backend logs.
- `serverTiming` is present, so server-side time can be separated from browser/network overhead.

Recommended smoke flows:

- Login
- Dashboard open
- Dashboard settings refresh
- Save notification preferences

## 3. Async notification tracing

Redis payloads now carry `_async_trace` metadata with:

- `correlation_id`
- `published_at`
- `producer`
- `queue_name`
- `event_name`

New producers also publish a soft-versioned envelope with:

- `version = v1`
- `meta`
- `payload`

Compatibility note:

- `trace_id` may still appear during transition, but it must mirror the same value as `correlation_id`.
- Root business fields and root `_async_trace` are still mirrored during transition so legacy consumers do not break while new consumers move to `meta` + `payload`.

The bot consumer logs this metadata on dequeue and after Telegram send, including `queue_latency_ms`.

Warning thresholds can be tuned with env vars:

- `ASYNC_QUEUE_LAG_WARN_MS`
- `ASYNC_NOTIFICATION_TOTAL_WARN_MS`

## 4. Manual probe commands

Use the probe script from the repo root:

```powershell
python scripts/test_redis_events.py --kind manager --user-id 123456789
python scripts/test_redis_events.py --kind broadcast --user-id 123456789 --text "Broadcast latency probe"
python scripts/test_redis_events.py --kind order-status --order-id ORD-00001
```

Notes:

- `manager` is the easiest end-to-end probe because it only needs configured manager chats.
- `broadcast` requires the target Telegram user/chat to be known by the bot.
- `order-status` requires a real order already present in storage, otherwise the consumer will log `Order not found`.

What to verify in logs:

- The same `correlation_id` appears across enqueue, dequeue, and send stages.
- `version=v1` appears on new producer log lines, while consumers still successfully process the message.
- `queue_latency_ms` on `stage=dequeued` stays below the expected local threshold.
- `total_latency_ms` on `stage=telegram_sent` stays below the end-to-end threshold.
- No `telegram_failed` stage appears for the probe event.

## 5. Release checklist

- Run `npm run build` in `front` and record the chunk sizes.
- Open the frontend with `VITE_ENABLE_REQUEST_TIMING=1` and verify console timing for login/settings flows.
- Trigger at least one manager notification probe and one broadcast probe.
- Confirm bot logs show `stage=dequeued` followed by `stage=telegram_sent` for the same `correlation_id`.
- Confirm the queued payload contains `version`, `meta`, and `payload` while still exposing compatibility mirrors for current consumers.
- If latency crosses the warning threshold, capture the `correlation_id` and the exact log lines before release.

## 6. Supporting Read-Model Follow-Up

These items are intentionally follow-up work, not implied release-ready features:

- Timeline aggregate read model:
  per-order timeline data exists, but there is no dedicated cross-order timeline feed yet.
- Compliance readiness read model:
  limits, whitelist, and profile documents exist as separate APIs, but there is no single backend readiness summary endpoint yet.
- Notification inbox read model:
  queue tracing exists for delivery diagnostics, but there is no persisted notification center API yet.

Review rule:

- Keep these surfaces documented as backend follow-ups until dedicated stable contracts exist.
