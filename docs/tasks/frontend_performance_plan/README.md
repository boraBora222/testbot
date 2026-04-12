# Frontend Performance Plan

This document captures the sequential frontend performance plan that was implemented for the current `React + Vite` application.

## Goal

Apply the most relevant `vercel-react-best-practices` ideas to the existing frontend with a focus on:

- reducing initial bundle pressure on the landing page
- removing avoidable async waterfalls
- loading translations conditionally
- shortening the auth-to-dashboard loading path without weakening route protection

## Scope

Primary files involved:

- `front/src/App.tsx`
- `front/src/components/blocks/Hero.tsx`
- `front/src/pages/dashboard/settings/index.tsx`
- `front/src/i18n/I18nContext.tsx`
- `front/src/i18n/I18nContext.shared.ts`
- `front/src/contexts/AuthContext.tsx`

## Sequential Tasks

1. Baseline audit
   - Build the frontend before changes.
   - Record the largest generated assets and use them as a comparison point for the rollout.
   - Result: completed.

2. Defer heavy landing page sections
   - Move `CalculatorWizard` out of the synchronous landing page render path.
   - Defer `ForWhom` and `HowItWorks` behind lazy boundaries.
   - Preserve section anchors so public navigation still works.
   - Result: completed.

3. Reduce motion on the critical path
   - Remove `framer-motion` from the synchronous `Hero` component.
   - Keep the same visual hierarchy with lightweight CSS-based entrance animation.
   - Result: completed.

4. Remove the settings refresh waterfall
   - Convert `SettingsPage.refresh()` from sequential requests to `Promise.all(...)`.
   - Keep current error handling and state updates explicit.
   - Result: completed.

5. Load translations conditionally
   - Keep Russian translations available synchronously as the default locale.
   - Load English translations on demand through a lazy import.
   - Avoid silent locale fallback behavior.
   - Result: completed.

6. Shorten the auth-to-dashboard path
   - Start dashboard route preloading during auth initialization.
   - Keep protected-route authorization rules unchanged.
   - Disable this preload side effect in test mode to avoid teardown races.
   - Result: completed.

7. Validate the rollout
   - Run focused frontend tests.
   - Run a production build after the changes.
   - Confirm that the main app chunk shrank and that route protection still behaves correctly.
   - Result: completed.

## Verification

Executed checks:

- `npm run test -- src/contexts/__tests__/AuthContext.test.tsx src/components/auth/__tests__/ProtectedRoute.test.tsx src/components/ui/loader/__tests__/PageLoader.test.tsx`
- `npm run build`

Validation outcome:

- targeted tests passed
- production build passed
- English translations were split into a separate chunk
- `CalculatorWizard`, `ForWhom`, and `HowItWorks` were moved out of the synchronous landing page path
- the main generated app chunk dropped from roughly `174.88 kB` to `127.32 kB` before gzip

## Notes

- `motion-vendor` still exists because several deferred or route-level components still use `framer-motion`, but it no longer needs to be pulled by the synchronous `Hero` component.
- Route security behavior was preserved. The preload optimization only affects fetch timing for route modules, not access control.
