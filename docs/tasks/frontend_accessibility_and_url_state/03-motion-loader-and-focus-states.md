# Task: Motion, Loader, And Focus States

- Objective: Replace broad transition declarations, add reduced-motion handling, and ensure shared interactive components keep explicit and visible focus behavior.
- Owner: Dev
- Dependencies: `01-navigation-and-semantic-links.md`, `02-forms-labels-and-icon-controls.md`
- Target Files:
  - `front/src/components/blocks/RequestModal.tsx`
  - `front/src/components/ui/loader/PageLoader.tsx`
  - `front/src/components/ui/tabs.tsx`
  - `front/src/index.css`
  - `front/src/pages/contacts/index.tsx`
- Success Criteria:
  - All reviewed `transition-all` and `transition: all` declarations are replaced with explicit property lists.
  - `RequestModal` respects `prefers-reduced-motion`.
  - `PageLoader` exposes loader announcement semantics through `role="status"` and/or `aria-live="polite"`.
  - `PageLoader` also respects `prefers-reduced-motion`.
  - Shared focus styling remains visible for tab triggers, icon buttons, and social links even where `outline-none` is used.
  - The requested loading text change is handled explicitly as part of the loader update.

## Steps

1. Replace broad transition declarations.
```text
- Review the flagged transition usage in `RequestModal.tsx`, `contacts/index.tsx`, and `index.css`.
- Replace each broad declaration with an explicit list of animated properties only.
- Keep timing and easing values only where they still match a real visual change.
```

2. Add reduced-motion handling to the request modal.
```text
- Review the current modal animation path and identify which parts are decorative rather than functional.
- Add a reduced-motion variant so opening and closing the modal does not rely on non-essential animation.
- Keep the visible state transition predictable for both standard and reduced-motion users.
```

3. Add loader announcement semantics and reduced-motion handling.
```text
- Update `PageLoader.tsx` so loading status is announced through `role="status"` and/or `aria-live="polite"`.
- Keep the loader text explicit and normalize the requested text change from `Loading...` to `Loading…`.
- Add a reduced-motion path so the loader does not force infinite decorative animation for users who prefer reduced motion.
```

4. Restore explicit focus-visible styling in shared UI primitives.
```text
- Review `tabs.tsx` where `outline-none` is currently used.
- Add a visible custom focus treatment if browser default outlines are removed.
- Keep the shared `.icon-button` and `.social-icon` focus styles aligned with the navigation work from phase 1.
```

## Validation

- Confirm `prefers-reduced-motion` users see stable state changes without unnecessary animation in the request modal and loader.
- Confirm screen readers announce the loader state once it appears.
- Confirm keyboard users can identify focus on tabs, social links, and icon buttons without relying on hover.
- Confirm no reviewed file retains the flagged broad transition declarations.
