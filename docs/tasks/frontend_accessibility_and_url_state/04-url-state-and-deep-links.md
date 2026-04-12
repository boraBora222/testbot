# Task: URL State And Deep Links

- Objective: Move shareable page state out of local-only React state and into explicit URL parameters or deep links where the page already represents a filterable or directly addressable view.
- Owner: Dev
- Dependencies: `roadmap.md`
- Target Files:
  - `front/src/pages/dashboard/deals/index.tsx`
  - `front/src/pages/faq/index.tsx`
  - `front/src/pages/legal/index.tsx`
  - `front/src/App.tsx`
- Success Criteria:
  - Dashboard deals filters are represented in the URL instead of only in component state.
  - FAQ search state is represented in the URL and restores correctly on refresh.
  - Legal sections can be opened directly from a URL deep link.
  - The implementation is compatible with the existing `HashRouter`.
  - Unknown URL values are handled explicitly and are not silently translated into another valid state.

## Steps

1. Document the `HashRouter` rules for this work.
```text
- Confirm the expected URL shape for this repo before implementation begins.
- Keep query-backed page state compatible with `#/path?...` behavior.
- Keep section deep links compatible with the current router setup and avoid patterns that appear valid but do not restore correctly after refresh.
```

2. Move dashboard deals filter state into the URL.
```text
- Replace the current local-only filter source of truth with query-backed state in `dashboard/deals/index.tsx`.
- Use one explicit query key for the filter and keep the supported values aligned with the page's allowed status values.
- Do not map unknown filter values to another supported filter; instead, reject or normalize them explicitly.
```

3. Move FAQ search state into the URL.
```text
- Sync the current FAQ search field with a stable query key.
- Ensure refresh, copy, and share behavior restore the same search state.
- If FAQ items later need direct item deep links, reserve that as an explicit extension instead of overloading the search parameter now.
```

4. Add legal page deep-link support.
```text
- Use the existing stable legal section identifiers as the deep-link target.
- Opening a legal deep link should expand the requested section only when the target is valid.
- Invalid section identifiers must not open some other legal section.
```

5. Keep parsing and serialization explicit.
```text
- Prefer a small parser/serializer local to each page over a generic abstraction introduced too early.
- Keep required parsing rules visible in the page module so filter state and deep-link behavior remain easy to audit.
- If URL cleanup is required, use explicit normalization rather than hidden fallback logic.
```

## Validation

- Confirm `/dashboard/deals` preserves the chosen filter after refresh and copy-paste.
- Confirm `/faq` restores the same search state after refresh and when opened in a new tab.
- Confirm `/legal` opens the requested valid section from a shared link.
- Confirm invalid query or section values do not silently activate a different filter or section.
