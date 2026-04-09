# Domain Boundaries And Service Facades

This document is the working boundary contract for the exchange track. It is intentionally short so it can be used during implementation and review without a larger architecture rewrite.

## Working Rule

- `exchange` is the default place for new product work.
- `legacy = compatibility only`.
- Existing legacy code can be patched for bug fixes, migrations, or integration shims that are required to keep the current product running.
- New exchange code must fail fast when required data is missing. No silent fallback, no substitute records, no fake success state, and no compatibility-only import added “just for now”.

## Ownership

- Exchange owner: dashboard, authenticated web API, exchange bot flow, whitelist/quota/profile/documents, orders, drafts, async order and manager notifications.
- Legacy owner: old moderation/admin contour, generic submission/admin pages, legacy data mirrors, and compatibility bridges kept only because current deployments still use them.
- Shared owner: `shared/` stays the runtime kernel, but new exchange use cases enter it through `shared/services`.

## Exchange Surfaces

- `front/src/` authenticated exchange UI and its API adapters, especially order, draft, profile, whitelist, and document flows.
- `web/routers/orders.py`, `web/routers/profile.py`, `web/routers/deals.py`, and exchange-facing support code under `web/`.
- `bot/crypto_exchange_bot.py` and exchange-specific bot states and handlers.
- `shared/exchange_logic.py`, `shared/security_settings.py`, `shared/async_tracing.py`, and exchange storage helpers in `shared/db.py`.
- `shared/services/` as the canonical entry point for exchange application behavior.

## Legacy Surfaces

- `web/routers/applications.py`, `web/routers/links.py`, and moderator/admin templates that serve the pre-exchange submission flow.
- Legacy link/material mirroring and legacy-only admin paths that still exist for compatibility.
- Generic moderator/broadcast support can touch exchange data, but it does not define new exchange contracts.

## Canonical Facades

New exchange code should import these facades from `shared.services`:

- `order_service`: order payload validation, draft lifecycle, repeat flow, status metadata, list/detail shaping.
- `profile_service`: whitelist creation/moderation, quota updates, order security checks.
- `document_service`: profile and deal document upload, download, delete, and audit helpers.

Implementation note:

- Existing direct imports from `shared.services.order_lifecycle`, `shared.services.security_settings`, and `shared.services.documents` may stay temporarily.
- New exchange scenarios should prefer `from shared.services import order_service, profile_service, document_service`.

## PR Rule

Every new exchange PR should satisfy all of the following:

- It belongs to an exchange surface listed above, or it explicitly states why a compatibility bridge is required.
- New application behavior enters `shared/` through `shared.services`.
- It does not add a new dependency from exchange code to legacy-only modules.
- It does not introduce silent fallback behavior, hidden retries, fake success wording, or substitute data when the backend contract is missing.

## Allowed Exceptions

- Compatibility patches in legacy surfaces are allowed when they unblock a current production path.
- A reviewed exception may temporarily keep a direct import if the facade is not ready yet, but the PR must call that out explicitly.
- If a required backend contract does not exist, document the gap and fail clearly instead of simulating completeness.
