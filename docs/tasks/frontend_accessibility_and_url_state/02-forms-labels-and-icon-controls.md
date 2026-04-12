# Task: Forms, Labels, And Icon Controls

- Objective: Normalize form semantics and icon-only control accessibility across the request modal, public forms, and auth flows, while keeping required field wiring explicit and consistent.
- Owner: Dev
- Dependencies: `01-navigation-and-semantic-links.md`
- Target Files:
  - `front/src/components/blocks/RequestModal.tsx`
  - `front/src/pages/contacts/index.tsx`
  - `front/src/pages/login/index.tsx`
  - `front/src/pages/register/index.tsx`
  - `front/src/pages/forgot-password/index.tsx`
  - `front/src/pages/verify-email/index.tsx`
  - `front/src/pages/reset-password/index.tsx`
  - `front/src/pages/dashboard/settings/index.tsx`
- Success Criteria:
  - All listed user-editable fields expose explicit `name` attributes.
  - Email and phone fields use the right `autocomplete` and input hints.
  - Close buttons and password-visibility toggle buttons expose explicit accessible names.
  - `RequestModal` submit disabling starts only after submission begins.
  - Requested ellipsis text is normalized to `Submitting... -> Submitting…` and `Loading... -> Loading…` in the relevant implementation files.
  - Shared field naming and labeling rules are documented clearly enough to apply consistently across the remaining frontend forms.

## Steps

1. Normalize field attributes in `RequestModal.tsx`.
```text
- Add `name` to the email field and set `autocomplete="email"`.
- Add `name` to the phone field and set the right `autocomplete` and `inputMode`.
- Keep required field handling explicit; do not rely on placeholder text or local state keys as a substitute for form attributes.
```

2. Fix the request modal icon-only close control and submit timing.
```text
- Add an explicit accessible name to the close button.
- Rework the submit-button rule so the button is not blocked before the request starts.
- Disable the button only for the active submission window and keep the submitting text change explicit.
```

3. Normalize contacts page form fields.
```text
- Add missing `name` attributes to the listed contact fields, including the email field and textarea.
- Add `autocomplete="email"` where the field collects email.
- Keep field names stable and purpose-driven so backend handling and browser autofill remain predictable.
```

4. Normalize auth form fields and password toggle buttons.
```text
- Add missing `name` attributes across login, register, forgot-password, verify-email, and reset-password forms.
- Add explicit accessible names to password-visibility toggle buttons in every listed auth page.
- If the same password-toggle pattern is repeated, reuse one small shared helper only if it reduces duplication without hiding the required button labeling behavior.
```

5. Document the dashboard settings form boundary.
```text
- Keep this phase focused on the shared field and control rules.
- If dashboard settings uses the same field conventions, note them here, but keep the page-specific label wiring and date-format cleanup in `05-dashboard-table-and-settings-hardening.md`.
- Do not split responsibility for the same settings-field fix across two implementation phases.
```

## Validation

- Confirm browser autofill recognizes email and phone fields where expected.
- Confirm screen readers announce close buttons and password toggles with explicit names.
- Confirm each listed form exposes stable `name` attributes for submitted fields.
- Confirm the request modal submit button remains available before submission begins and becomes disabled only during the active request.
