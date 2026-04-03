# Task: Telegram Bot Profile and Order Flow

- Objective: Bring the Telegram bot in line with the same limits, whitelist, and order-creation rules used by the dashboard and backend APIs.
- Owner: Dev
- Dependencies: `02-profile-limits-and-notifications-api.md`, `03-whitelist-crud-and-moderation.md`, `04-order-enforcement-and-quota-accounting.md`, [Client security settings specification](../../specifications/client_security_settings.md)
- Success Criteria:
  - `/profile` shows daily and monthly limits, usage, and remaining balance.
  - Order creation in the bot uses active whitelist selection instead of unchecked free-form address submission.
  - Manual address entry cannot complete an order unless the address becomes approved through the whitelist flow.
  - The bot guides the user to submit a new address for moderation when needed.

## Steps

1. Extend the bot profile view.
```text
- Update `/profile` to show daily and monthly limits, used amount, and remaining amount.
- Keep the bot output consistent with the profile limits API so values do not drift between channels.
```

2. Update the order creation entry flow.
```text
- Present active whitelist addresses as the primary address-selection mechanism.
- Carry wallet network and whitelist identity through the bot order flow.
- Keep the bot UX aligned with backend order enforcement instead of maintaining a separate rule set.
```

3. Restrict manual address input behavior.
```text
- Allow manual entry only as a step toward whitelist submission.
- If the address is not active, stop order completion and explain that moderation is required first.
- Offer the next action to submit the address to whitelist review.
```

4. Align bot messaging with the approved policy.
```text
- Use the same single whitelist wording as the dashboard and FAQ.
- Keep limit overflow messaging informational and manager-visible, not phrased as a hard rejection.
- Avoid stale copy that implies the whitelist is checked only after request creation.
```

## Validation

- Confirm section `6.2` is fully implemented in the bot flow.
- Confirm the bot cannot create an order to an address outside the active whitelist.
- Confirm the bot and dashboard present the same product rule and the same limit semantics.
