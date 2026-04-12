# Task: Navigation And Semantic Links

- Objective: Replace non-semantic navigation controls in shared layout components with real links, add accessible names to icon-only navigation links, and harden related shared focus and transition styles.
- Owner: Dev
- Dependencies: `roadmap.md`
- Target Files:
  - `front/src/components/layout/Header.tsx`
  - `front/src/components/layout/Footer.tsx`
  - `front/src/index.css`
- Success Criteria:
  - Header navigation no longer uses `button + navigate(...)` for route changes.
  - Mobile navigation in the header also uses semantic links.
  - Footer navigation to public sections uses `Link` or `a` instead of `button`.
  - Telegram icon links in header and footer expose an explicit accessible name.
  - Shared icon-link styles keep a visible `:focus-visible` state.
  - The reviewed header transition declarations no longer use `transition-all`.

## Steps

1. Replace desktop navigation actions in the header.
```text
- Review all route-changing controls in `Header.tsx`.
- Convert every control that changes location to `Link` or `a`, depending on whether the target is an internal route or an external destination.
- Preserve the current visual styling and active-state behavior while removing imperative `navigate(...)` usage from purely navigational UI.
```

2. Replace mobile navigation actions in the header.
```text
- Apply the same semantic-link pattern to the mobile menu controls.
- Keep menu open/close behavior separate from route navigation behavior.
- Ensure the mobile menu still supports the current interaction flow without relying on `button` for page changes.
```

3. Add accessible names to icon-only social links.
```text
- Add an explicit accessible name to the Telegram link in `Header.tsx`.
- Add an explicit accessible name to the Telegram link in `Footer.tsx`.
- Use one stable naming pattern so the same destination is announced consistently in both layout components.
```

4. Harden shared focus-visible and interaction styling.
```text
- Review `.social-icon` and `.icon-button` in `index.css`.
- Add or refine explicit `:focus-visible` states so keyboard users can track focus without relying on browser defaults that may already be removed.
- Keep hover and focus styling aligned, but do not make focus depend on hover-only styling.
```

5. Narrow transition declarations.
```text
- Replace the flagged `transition-all` usage in `Header.tsx` with explicit transitioned properties only.
- Keep the property list limited to the values that actually animate in the component.
- Avoid broad transition declarations in shared navigation styles going forward.
```

## Validation

- Confirm tab navigation reaches header links, footer links, and Telegram icon links in a predictable order.
- Confirm screen readers announce the Telegram links with an explicit name instead of only reading the icon or URL.
- Confirm route changes still work for desktop and mobile navigation after replacing `button` controls.
- Confirm no reviewed shared layout control loses visible focus indication.
