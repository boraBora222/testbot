# Task: Dashboard Settings Integration

- Objective: Replace the current dashboard placeholders with the real client security settings experience on `/dashboard/settings`.
- Owner: Dev
- Dependencies: `02-profile-limits-and-notifications-api.md`, `03-whitelist-crud-and-moderation.md`, [Client security settings specification](../../specifications/client_security_settings.md)
- Success Criteria:
  - `/dashboard/settings` uses real APIs instead of mocks.
  - The page shows daily and monthly limit progress with actual usage values.
  - Notification settings can be viewed and saved from the dashboard.
  - Whitelist entries display moderation status, including rejection reason and support CTA.
  - Dashboard copy uses the single whitelist rule from the specification.

## Steps

1. Replace mock data sources.
```text
- Remove placeholder data and connect the settings page to profile limits,
  notification preferences, and whitelist APIs.
- Keep the page contract aligned with backend responses rather than adding frontend fallbacks.
```

2. Render the limits block.
```text
- Show daily and monthly limit values, current usage, and remaining balance.
- Present progress clearly enough for informational warning flows.
- Keep reset timing visible if the backend contract exposes it.
```

3. Render and persist notification settings.
```text
- Show channel toggles for `telegram` and `email`.
- Show per-event toggles for the four supported events only.
- Save user changes through the dedicated profile notifications update API.
```

4. Render whitelist states and actions.
```text
- Show entries grouped or labeled by moderation state.
- Surface `pending`, `active`, and `rejected` clearly.
- For rejected entries, show the reject reason and a support-oriented CTA.
```

5. Align dashboard copy with product rules.
```text
- Remove any text that suggests post-request checks or first-deal-only verification.
- Use the unified rule that deals can be created only to active whitelist addresses.
- Keep displayed daily limit values aligned with the system defaults from the specification.
```

## Validation

- Confirm section `6.1` is fully represented on the dashboard without mock behavior.
- Confirm the page cannot imply that a user may complete an order to a non-whitelisted address.
- Confirm all dashboard labels and help text match the synchronized release wording.
