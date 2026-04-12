# Task: Dashboard Table And Settings Hardening

- Objective: Resolve dashboard-specific accessibility and semantics issues in the deals table and settings page without reintroducing non-semantic interaction patterns.
- Owner: Dev
- Dependencies: `01-navigation-and-semantic-links.md`, `02-forms-labels-and-icon-controls.md`, `04-url-state-and-deep-links.md`
- Target Files:
  - `front/src/components/dashboard/DealsTable.tsx`
  - `front/src/pages/dashboard/settings/index.tsx`
- Success Criteria:
  - `DealsTable` no longer relies on a clickable `tr` for primary navigation.
  - The main deal navigation target is exposed through a keyboard-accessible control inside a table cell.
  - Dashboard settings labels are correctly associated with their controls.
  - Dashboard settings fields expose the required `id` and `name` attributes where missing.
  - Settings date formatting uses `Intl.DateTimeFormat` instead of direct `toLocaleString('ru-RU', ...)`.

## Steps

1. Replace row-level deal navigation with a semantic in-cell action.
```text
- Remove the current pattern where the full table row acts as the navigation target.
- Move primary navigation into a `Link` or clearly labeled button inside a meaningful table cell.
- Keep row usability high, but do not depend on custom keyboard emulation for a clickable `tr`.
```

2. Settle one explicit dashboard table navigation pattern.
```text
- Decide whether the semantic navigation target lives in the deal title cell, a dedicated action cell, or another stable location.
- Apply the same pattern to every row so screen-reader and keyboard behavior stays predictable.
- Keep any secondary row actions separate from the main navigation target.
```

3. Fix dashboard settings label and field wiring.
```text
- Associate each flagged label with its actual control.
- Add explicit `id` and `name` attributes to inputs and selects where they are missing.
- Keep field names stable and descriptive rather than inferred from placeholder or local state usage.
```

4. Replace ad hoc date formatting.
```text
- Replace direct `toLocaleString('ru-RU', ...)` usage with an `Intl.DateTimeFormat` instance.
- Keep the formatter explicit in configuration and reuse it locally if the page formats the same value more than once.
- Do not hide missing or invalid date inputs behind invented fallback strings.
```

## Validation

- Confirm keyboard users can open a deal from the table without depending on row-level click behavior.
- Confirm screen readers announce one clear navigation target per deal row.
- Confirm settings labels activate or describe the correct control.
- Confirm formatted settings dates remain stable and locale-explicit after the formatter change.
