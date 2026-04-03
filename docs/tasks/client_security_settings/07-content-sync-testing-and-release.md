# Task: Content Sync, Testing, and Release

- Objective: Finalize wording, validation coverage, and release readiness for the client security settings package across backend, dashboard, bot, and admin flows.
- Owner: Dev + QA
- Dependencies: `01-domain-models-and-validation.md`, `02-profile-limits-and-notifications-api.md`, `03-whitelist-crud-and-moderation.md`, `04-order-enforcement-and-quota-accounting.md`, `05-dashboard-settings-integration.md`, `06-telegram-bot-profile-and-order-flow.md`
- Success Criteria:
  - FAQ and UI wording match the final whitelist policy and daily limit values.
  - Acceptance criteria from the specification can be checked directly against implemented flows.
  - Non-functional requirements for validation, atomicity, performance, reset timing, and async notifications are explicitly verified.
  - Release readiness covers backend, dashboard, bot, admin, and content synchronization.

## Steps

1. Synchronize product wording.
```text
- Remove wording such as "Whitelist check after request" and
  "Address verification is required for the first deal".
- Apply one unified rule: withdrawals and deals are allowed only to active whitelist addresses.
- Verify displayed daily limit values match the system contract for `basic`, `extended`, and `corporate`.
```

2. Execute acceptance validation.
```text
- Verify limit visibility in dashboard and Telegram bot.
- Verify notification settings persistence and scope.
- Verify whitelist add/view/delete behavior and moderator approval or rejection.
- Verify order creation is blocked for non-active whitelist addresses.
- Verify order records preserve whitelist linkage or manual-source provenance.
- Verify admin limit edits create audit history.
```

3. Execute non-functional validation.
```text
- Verify address format validation in frontend, API, and bot.
- Verify quota usage updates are atomic.
- Verify daily reset happens at `00:00 UTC` and monthly reset at `00:00 UTC` on day one of the month.
- Verify `GET /api/profile/limits` meets the target latency expectation.
- Verify user notifications are dispatched asynchronously and do not block order creation.
```

4. Prepare rollout sign-off.
```text
- Check backend, admin, dashboard, and bot for consistent whitelist and limit behavior.
- Confirm no excluded scope from the specification was silently implemented as half-supported behavior.
- Record any operational assumptions that must be known before release.
```

## Validation

- Confirm sections `7`, `8`, and `9` of the specification are converted into an actionable release checklist.
- Confirm wording and behavior stay synchronized across FAQ, dashboard, bot, and admin views.
- Confirm release sign-off covers both happy paths and policy-enforcement scenarios.
