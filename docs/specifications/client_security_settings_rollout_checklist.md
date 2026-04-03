# Client Security Settings Rollout Checklist

This document turns sections `7`, `8`, and `9` of `docs/specifications/client_security_settings.md` into a release-facing verification matrix for backend, dashboard, Telegram bot, admin flows, and public content.

## Product Wording Sync

| Surface | Expected Result | Coverage |
| --- | --- | --- |
| Public calculator copy | No wording remains about whitelist checks happening after request creation or only for the first deal | Automated + Review |
| FAQ copy | Whitelist text states that deals and withdrawals are allowed only to active whitelist addresses | Automated + Review |
| FAQ and dashboard limits copy | Displayed daily values match `basic 1,000,000 ₽/day`, `extended 10,000,000 ₽/day`, `corporate custom` | Automated + Review |
| Dashboard settings page | Header and helper text use the same active-whitelist rule as the backend and bot | Automated + Review |
| Telegram bot whitelist flow | Bot prompts state that only active whitelist addresses can be used to complete an order | Automated |
| API rejection wording | Order rejection for a non-approved wallet explicitly refers to the active whitelist requirement | Automated |

## Acceptance Verification Matrix

| Scenario | Expected Result | Coverage |
| --- | --- | --- |
| Dashboard limits view | User sees daily and monthly limits, usage, remaining balance, and reset timestamps | Automated + Manual |
| Telegram `/profile` view | Bot shows the same daily and monthly semantics as the dashboard | Automated + Manual |
| Notification settings persistence | Only `telegram` and `email` channels are configurable, and only user notifications are affected | Automated |
| Whitelist add/view/delete flow | User can create a `pending` entry, review statuses, and delete a non-active entry | Automated + Manual |
| Manager moderation flow | Admin can approve or reject a pending whitelist address and store a rejection reason | Automated + Manual |
| Order creation enforcement | Orders cannot be created to addresses outside the active whitelist | Automated |
| Order provenance | Persisted orders keep whitelist linkage or manual-source provenance fields | Automated |
| Limit audit history | Admin limit edits create an audit record tied to the change | Automated |

## Non-Functional Verification Matrix

| Check | Expected Result | Coverage |
| --- | --- | --- |
| Address validation parity | Address format validation is enforced in frontend, API, and bot for TRC-20, ERC-20, and BEP-20 | Automated |
| Quota update atomicity | Daily and monthly usage counters are updated atomically with order creation | Automated + Review |
| Reset timing | Daily reset happens at `00:00 UTC`; monthly reset happens at `00:00 UTC` on the first day of the month | Automated |
| Profile limits latency | `GET /api/profile/limits` meets the target expectation in the deployed environment | Manual |
| Async notification delivery | User notifications are dispatched asynchronously and do not block successful order creation | Review + Manual |

## Operational Assumptions And Scope Guards

- The package stays strictly `user_id` scoped in v1. No company-scoped fallback behavior is silently introduced.
- Supported notification channels remain limited to `telegram` and `email`.
- Supported whitelist networks remain limited to `TRC-20`, `ERC-20`, and `BEP-20`.
- Limit overflow stays a warning for manager review and does not become a hard order-creation block.
- Whitelist moderation remains a manual admin action; there is no silent auto-approval path in rollout.
- Performance validation for `GET /api/profile/limits` must be measured against the target environment, not inferred only from unit tests.

## Suggested Release Checks

1. Run the backend security-settings suite and confirm dashboard, orders, admin, and bot tests pass together.
2. Build the frontend and verify `/dashboard/settings` renders without mock-only copy or stale whitelist wording.
3. Manually verify FAQ, dashboard, bot, and admin screens use the same active-whitelist policy.
4. Confirm a non-active wallet cannot complete order creation from either dashboard or Telegram bot.
5. Confirm admin moderation and limit editing both leave auditable results.
6. Record any deployment-specific observations about queue workers, moderation operations, or latency before sign-off.

## Release Sign-Off

The release can be signed off only when all items below are true:

1. Product wording is synchronized across FAQ, calculator, dashboard, bot, and API error flows.
2. Acceptance scenarios from section `8` of the specification are covered by explicit automated or manual checks.
3. Non-functional requirements from section `7` are validated or explicitly assigned as deployment checks.
4. Content updates from section `9` are reflected in the shipped UI and documentation.
5. Backend, dashboard, Telegram bot, admin, and operational stakeholders share one final checklist for release readiness.
