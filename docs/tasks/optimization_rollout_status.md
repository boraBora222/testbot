# Frontend Optimization Rollout Status

This document is the execution-facing companion for the optimization rollout plan. It tracks the current delivery scope, the baseline measurement contract, and the implementation order for the frontend performance work.

## Goal

Improve dashboard responsiveness and route performance in the React/Vite frontend without changing public component APIs, backend contracts, routing behavior, or product UX. All performance regressions must stay explicit; no silent fallback paths are allowed.

## Baseline Measurement Contract

### Route scenarios

- `dashboard-route`: measure dashboard entry to meaningful paint.
- `dashboard-deals-route`: measure deals list entry to meaningful paint.
- `dashboard-deal-detail-route`: measure deal detail entry to meaningful paint.
- `dashboard-settings-route`: measure settings entry to meaningful paint.
- `dashboard-new-deal-route`: measure new-deal entry to meaningful paint.

### Interaction scenarios

- `dashboard-new-deal-typing`: measure typing responsiveness while preview state updates.
- `dashboard-deals-filter-change`: measure filter switch on the deals list.
- `dashboard-new-deal-step-transition`: measure draft-backed step transitions.
- `dashboard-deal-document-download`: measure document download start on deal detail.
- `dashboard-modal-open`: reserve for alert-dialog and dropdown opening checks.

### Acceptance budgets

- Dashboard route meaningful paint: `< 250 ms` on warm path.
- New-deal route meaningful paint: `< 200 ms` on warm path.
- INP for dashboard interactions: `< 200 ms`.
- CLS for dashboard screens: `< 0.05`.
- Long task budget: `0` avoidable tasks over `50 ms` during hot interactions.
- Forced reflow budget: no repeated read/write/read layout thrashing in measured flows.

## Implementation Order

### Phase 1. Baseline and instrumentation

Status: implemented in progress

- Add performance scenario identifiers and budgets in `front/src/config/performance.ts`.
- Add reusable performance helpers in `front/src/lib/performance.ts`.
- Add route timing hook in `front/src/hooks/useRoutePerformance.ts`.
- Wire hot dashboard routes to the measurement hook before deeper refactors.

### Phase 2. Provider and route-shell stabilization

Status: implemented in progress

- Stabilize `ThemeProvider` and `I18nProvider` context values.
- Remove unnecessary page subscriptions to theme state by letting `Header` read theme context directly.
- Keep dashboard loading geometry stable with dedicated route fallbacks.
- Add route chunk preloading on dashboard intent paths.

### Phase 3. Dashboard section isolation

Status: implemented in progress

- Add deferred, contained below-the-fold sections with `content-visibility` and `contain`.
- Isolate secondary dashboard/detail/settings sections from initial route render.
- Memoize table rows and reduce repeated list work where profiling shows churn.
- Keep upload and document state local to their sections.

### Phase 4. Hot interaction cleanup and validation

Status: implemented in progress

- Defer non-critical preview computation in the new-deal flow.
- Audit scroll, animation, and count-up paths for avoidable frame work.
- Add intent-driven preload coverage and focused regression tests.
- Re-run dashboard test suites, lint, and build after the rollout lands.

## Primary Files

- `front/src/App.tsx`
- `front/src/components/layout/Header.tsx`
- `front/src/contexts/AuthContext.tsx`
- `front/src/contexts/ThemeContext.tsx`
- `front/src/i18n/I18nContext.tsx`
- `front/src/pages/dashboard/index.tsx`
- `front/src/pages/dashboard/deals/index.tsx`
- `front/src/pages/dashboard/deals/[id].tsx`
- `front/src/pages/dashboard/new-deal/index.tsx`
- `front/src/pages/dashboard/settings/index.tsx`
- `front/src/components/dashboard/DealsTable.tsx`
- `front/src/components/dashboard/ProfileDocumentsSection.tsx`
- `front/src/components/dashboard/MetricsCard.tsx`
- `front/src/hooks/useCountUp.ts`

## Verification Checklist

- Route timings are emitted for all dashboard pages listed above.
- Dashboard pages no longer subscribe to theme context only to pass props into `Header`.
- Below-the-fold heavy sections are rendered through contained or deferred boundaries.
- New-deal preview computation is no longer directly coupled to every keystroke.
- Route preloading is triggered by dashboard navigation intent.
- `npm run test:dashboard-orders`, `npm run lint`, and `npm run build` pass after the rollout.
