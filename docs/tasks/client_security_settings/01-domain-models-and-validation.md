# Task: Domain Models and Validation

- Objective: Establish the data contracts, validation rules, and storage boundaries required for client limits, notification preferences, whitelist addresses, and order-to-whitelist linkage.
- Owner: Dev
- Dependencies: [Client security settings specification](../../specifications/client_security_settings.md), existing user, order, and admin data modules
- Success Criteria:
  - `ExchangeUserDB` has a documented `notification_preferences` block with `telegram` and `email` controls only.
  - Storage contracts exist for `limit_quotas`, `limit_quota_history`, and `whitelist_addresses`.
  - `OrderDB` has explicit fields for whitelist linkage and wallet address source.
  - Validation rules are defined for supported networks, whitelist limits, duplicate prevention, and rejected-address resubmission rules.
  - The package remains `user_id` scoped in v1 with no hidden company-level fallback behavior.

## Steps

1. Extend the user profile data contract.
```text
- Add an embedded `notification_preferences` block to `ExchangeUserDB`.
- Keep only `telegram_enabled`, `email_enabled`, and the four event toggles:
  `order_created`, `order_status_changed`, `support_reply`, `limit_warning`.
- Do not reintroduce `sms_enabled` or any speculative channels.
```

2. Define quota storage contracts.
```text
- Introduce `limit_quotas` with daily and monthly limits, usage counters, reset timestamps,
  verification level, and update timestamp.
- Introduce `limit_quota_history` for admin audit entries with actor, field, old/new values,
  reason, and creation timestamp.
- Keep the quota contract explicit so later API and admin work can rely on stable field names.
```

3. Define whitelist storage contracts.
```text
- Introduce `whitelist_addresses` with `user_id`, `network`, `address`,
  `address_normalized`, `label`, moderation status, rejection metadata, and timestamps.
- Document the unique identity rule as `user_id + network + address_normalized`.
- Keep the lifecycle limited to `pending`, `active`, and `rejected`.
```

4. Extend the order contract for wallet provenance.
```text
- Add `address_source`, `whitelist_address_id`, `wallet_address`, and `wallet_network`.
- Make the whitelist reference mandatory when an order uses a whitelist address.
- Preserve the distinction between approved whitelist selection and manual input flow.
```

5. Define shared validation rules.
```text
- Support only `TRC-20`, `ERC-20`, and `BEP-20`.
- Validate address format at every boundary that accepts wallet input.
- Enforce a maximum of 5 addresses in `pending` and `active` combined.
- Reject repeated submission of an address that already exists in `rejected`.
- Keep validation fail-fast and explicit instead of masking invalid state with defaults.
```

## Validation

- Review sections `3`, `4`, and `7` of the specification and confirm that every required field has a clear storage destination.
- Confirm the contract preserves `user_id` scope for v1 and does not introduce company-level ambiguity.
- Confirm all whitelist and notification rules are expressed as hard validation rules, not UI-only guidance.
