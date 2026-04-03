# Task: Profile Limits and Notifications API

- Objective: Deliver the client-facing profile API for limit visibility and notification preference management on top of the finalized storage contracts.
- Owner: Dev
- Dependencies: `01-domain-models-and-validation.md`, [Client security settings specification](../../specifications/client_security_settings.md)
- Success Criteria:
  - `GET /api/profile/limits` returns daily and monthly limits, usage, and remaining amount.
  - `GET /api/profile/notifications` returns the current notification preference state.
  - `PUT /api/profile/notifications` persists user-controlled notification settings.
  - Only `telegram` and `email` channels are exposed.
  - API contracts remain aligned with dashboard and bot profile needs.

## Steps

1. Implement the limits read model.
```text
- Expose daily limit, daily used, daily remaining, monthly limit, monthly used,
  monthly remaining, and reset timestamps.
- Keep the response contract explicit so the dashboard and bot can render progress
  without guessing or deriving missing fields on the client.
```

2. Implement the notification preferences read endpoint.
```text
- Return channel toggles for `telegram` and `email`.
- Return per-event toggles for `order_created`, `order_status_changed`,
  `support_reply`, and `limit_warning`.
- Do not expose unsupported channels or deprecated placeholder fields.
```

3. Implement the notification preferences update endpoint.
```text
- Validate the full request payload before persistence.
- Persist only the supported preference fields from the specification.
- Fail fast on invalid event keys or malformed channel values.
```

4. Align response contracts with product behavior.
```text
- Treat limits as informational values that can drive warnings later, not as a hard-block API.
- Keep manager-only notifications out of this user preference surface.
- Document any fields the dashboard and bot can safely rely on as source of truth.
```

## Validation

- Confirm the profile API fully covers section `5.1` for limits and notifications.
- Confirm response fields are sufficient for `/dashboard/settings` and Telegram `/profile`.
- Confirm the API does not invent fallback channels, fallback events, or derived defaults for missing required data.
