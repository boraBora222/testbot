# Task: Order Enforcement and Quota Accounting

- Objective: Connect whitelist approval, order creation, limit usage tracking, and admin quota audit into one consistent backend flow.
- Owner: Dev
- Dependencies: `01-domain-models-and-validation.md`, `02-profile-limits-and-notifications-api.md`, `03-whitelist-crud-and-moderation.md`, [Client security settings specification](../../specifications/client_security_settings.md)
- Success Criteria:
  - Order creation accepts only addresses from the user's `active` whitelist.
  - Manual address entry is treated only as a candidate for whitelist submission, not as a bypass path.
  - Orders persist address provenance with `address_source`, `whitelist_address_id`, `wallet_address`, and `wallet_network`.
  - Daily and monthly quota usage is updated atomically.
  - Admin limit edits create audit records in `limit_quota_history`.

## Steps

1. Enforce whitelist rules during order creation.
```text
- Require an `active` whitelist match before an order can be created successfully.
- Keep manual address input only as a preliminary step for validation and later whitelist submission.
- Return a product-aligned rejection when the address is not approved yet.
```

2. Persist wallet provenance in the order model.
```text
- Save `address_source` as `whitelist` or `manual`.
- Require `whitelist_address_id` whenever the order is linked to an approved address.
- Persist the wallet address and network used for the final order record.
```

3. Implement quota accounting updates.
```text
- Increment daily and monthly usage atomically during the order flow.
- Preserve independent reset timestamps for daily and monthly counters.
- Keep overflow behavior informational: create the order, record the usage, and surface a warning.
```

4. Wire admin limit edit audit.
```text
- Add or finalize the admin limit edit action.
- On every limit change, write audit rows with actor, field, old value, new value, reason, and timestamp.
- Keep client history out of scope for v1 even though admin audit is mandatory.
```

5. Prepare downstream notification triggers.
```text
- Make limit-overflow warnings and order status events compatible with asynchronous notification delivery.
- Do not block order creation on notification dispatch.
- Keep manager notification logic separate from user preference enforcement.
```

## Validation

- Confirm the implementation covers sections `3.2`, `3.4`, `4.5`, `6.2`, `7`, and `8` of the specification.
- Confirm the limit rule remains warning-only and does not become an accidental hard block.
- Confirm quota updates and whitelist checks cannot succeed with partial state or detached audit linkage.
