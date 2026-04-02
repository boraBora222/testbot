# Authorization Implementation Roadmap

This roadmap defines the recommended execution order for the authorization work so the team can use it as a reference during implementation.

## Goal

Deliver the authorization feature in a safe sequence that respects technical dependencies, reduces rework, and keeps backend and frontend integration aligned with the specification.

## Recommended Execution Order

### Phase 1. Foundation and contracts

Start with:
- ~~`01-auth-foundation-and-config_done.md`~~

Why first:
- all other tasks depend on the auth data model, repository contract, configuration surface, and request/response schemas
- this phase defines the storage and API contracts that backend and frontend work will rely on

Main outputs:
- auth models in `shared/models.py`
- auth repository functions in `shared/db.py`
- auth and SMTP settings in `web/config.py`
- request and response schemas in `web/models.py`

Exit criteria:
- the backend auth domain has stable contracts
- env variable mapping is defined
- moderator Basic Auth remains explicitly separated from user auth

### Phase 2. Core session auth

Then implement:
- ~~`02-session-auth-api_done.md`~~

Why second:
- frontend auth cannot be migrated safely before `/auth/register`, `/auth/login`, `/auth/logout`, and `/auth/me` exist
- email verification and password reset should reuse the same auth helpers and session model

Main outputs:
- password hashing and verification
- cookie helpers
- current-user resolution from session cookie
- working session-based auth endpoints

Exit criteria:
- register/login/logout/me are operational
- every successful login or registration creates a fresh session
- `/auth/me` becomes the backend source of truth for auth state

### Phase 3. Verification and password reset

After core auth, implement in parallel where possible:
- ~~`03-email-verification_done.md`~~
- ~~`04-password-reset_done.md`~~

Why here:
- both flows depend on the user model, config, repository helpers, and email delivery
- both share one-time code generation, hashing, expiry, and attempt-limit concepts

Recommended internal order:
1. Create shared one-time-code helpers and SMTP email service.
2. Implement email verification.
3. Implement password reset and session invalidation.

Main outputs:
- SMTP-backed email service
- verification code issue and confirmation flow
- password reset request and confirmation flow
- invalidation of all sessions after successful password reset

Exit criteria:
- verification works end-to-end
- password reset works end-to-end
- codes are hashed, time-limited, single-use, and never logged

### Phase 4. Frontend migration

After backend contracts are stable, implement:
- ~~`05-frontend-auth-flow_done.md`~~

Why after backend:
- the frontend must integrate with finalized backend endpoint contracts
- `AuthContext` and protected routes should use real backend auth state instead of mock state

Main outputs:
- `front/src/config/service.ts` updated with auth API methods
- `credentials: "include"` on auth requests
- `AuthContext` initialized from `/auth/me`
- auth pages updated for login, register, verify email, forgot password, and reset password
- `ProtectedRoute` driven by context, not `localStorage`

Exit criteria:
- frontend auth state is restored only through `/auth/me`
- mock auth and `localStorage` auth dependencies are removed
- all auth screens follow the backend response contract

### Phase 5. Security hardening and platform wiring

Finalize cross-cutting requirements with:
- `06-security-cors-and-observability_done.md`

Why now:
- some security rules must be respected from the beginning, but this phase is where the implementation is reviewed and finalized as a whole
- CORS and cookie delivery should be validated against the fully integrated frontend and backend

Main outputs:
- explicit CORS configuration with credentials enabled
- cookie security settings aligned with configuration
- anti-enumeration responses confirmed
- safe logging expectations applied
- Redis migration boundaries preserved

Exit criteria:
- cookies are delivered correctly cross-origin
- sensitive data is not exposed in logs, responses, or browser storage
- MVP boundaries are clear and no hidden fallback behavior is introduced

### Phase 6. Validation and release readiness

Finish with:
- `07-testing-rollout-and-dod_done.md`

Why last:
- validation is meaningful only after backend and frontend flows are in place
- Definition of Done should be checked against the actual implemented system

Main outputs:
- backend validation matrix
- frontend validation matrix
- security regression coverage
- rollout and environment readiness checklist

Exit criteria:
- all required auth flows are verified
- moderator auth regression is checked
- DoD from the specification is satisfied

## Parallel Work Opportunities

The following work can be done in parallel after the required prerequisites are complete:

- ~~`03-email-verification_done.md`~~ and ~~`04-password-reset_done.md`~~ can run in parallel after `01` and `02`
- ~~`05-frontend-auth-flow_done.md`~~ can begin once the core backend auth API is stable
- `06-security-cors-and-observability_done.md` can be reviewed continuously, but final closure should happen after backend and frontend integration

## Dependency Map

- ~~`01-auth-foundation-and-config_done.md`~~ -> prerequisite for all other tasks
- ~~`02-session-auth-api_done.md`~~ -> depends on `01`
- ~~`03-email-verification_done.md`~~ -> depends on `01` and shared auth helpers from `02`
- ~~`04-password-reset_done.md`~~ -> depends on `01`, `02`, and shared email/code helpers
- ~~`05-frontend-auth-flow_done.md`~~ -> depends on stable backend auth endpoints from `02`, and is completed more safely once `03` and `04` are defined
- `06-security-cors-and-observability_done.md` -> depends on implemented backend and frontend flows
- `07-testing-rollout-and-dod_done.md` -> depends on completion of all prior implementation work

## Suggested Milestones

### Milestone 1. Backend auth foundation

Includes:
- ~~`01-auth-foundation-and-config_done.md`~~
- ~~`02-session-auth-api_done.md`~~

Outcome:
- the service supports session-based auth with cookies and `/auth/me`

### Milestone 2. Recovery and trust flows

Includes:
- ~~`03-email-verification_done.md`~~
- ~~`04-password-reset_done.md`~~

Outcome:
- users can verify email and reset passwords securely

### Milestone 3. Frontend migration

Includes:
- ~~`05-frontend-auth-flow_done.md`~~

Outcome:
- frontend auth is fully server-driven and no longer depends on mock state or browser storage

### Milestone 4. Hardening and sign-off

Includes:
- `06-security-cors-and-observability_done.md`
- `07-testing-rollout-and-dod_done.md`

Outcome:
- the feature is security-reviewed, validated, and ready for release

## Practical Team Split

### Single developer sequence

1. Complete ~~`01`~~
2. Complete ~~`02`~~
3. Build shared email and one-time-code helpers
4. Complete ~~`03`~~
5. Complete ~~`04`~~
6. Complete ~~`05`~~
7. Complete `06`
8. Complete `07`

### Two-stream sequence

Stream A:
- ~~`01`~~
- ~~`02`~~
- `06`

Stream B:
- start `05` after the core backend auth API is stable

Shared follow-up:
- ~~`03`~~
- ~~`04`~~
- `07`

## Implementation Notes

- Do not start frontend migration before `/auth/me`, `register`, `login`, and `logout` are stable.
- Keep moderator Basic Auth untouched throughout implementation.
- Treat Redis rate limiting as a planned extension unless explicitly included in active implementation scope.
- Keep all auth-related business rules fail-fast and avoid hidden fallbacks.
