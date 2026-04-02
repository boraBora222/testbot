# Task: Testing, Rollout, and Definition of Done

- Objective: Turn the authorization specification checklist into an execution and sign-off plan for backend, frontend, security, and rollout validation.
- Owner: Dev + QA
- Dependencies: `01-auth-foundation-and-config_done.md`, `02-session-auth-api_done.md`, `03-email-verification_done.md`, `04-password-reset_done.md`, `05-frontend-auth-flow_done.md`, `06-security-cors-and-observability_done.md`
- Success Criteria:
  - The repository has a clear verification matrix for the eight auth endpoints and related frontend behavior.
  - Security-sensitive scenarios are explicitly tested, including user-enumeration boundaries and session invalidation after password reset.
  - Environment readiness and rollout limitations are documented before release.
  - Completion can be checked directly against the specification Definition of Done.

## Steps

1. Cover backend auth happy paths.
```text
- Test register success.
- Test login success.
- Test logout success.
- Test `/auth/me` with a valid session cookie.
- Test password reset followed by login with the new password.
```

2. Cover backend auth failures and security edges.
```text
- Test `/auth/me` with missing, invalid, and expired sessions.
- Test duplicate registration rejection.
- Test invalid email and weak password rejection.
- Test invalid, expired, and over-limit verification/reset codes.
- Test that password reset invalidates all previous sessions.
- Test that verification/reset request responses do not leak whether the email exists.
```

3. Cover frontend auth behavior.
```text
- Verify auth state is restored only through `/auth/me`.
- Confirm protected routes redirect unauthenticated users.
- Confirm login, register, verify-email, forgot-password, and reset-password pages follow the backend contract.
- Confirm the frontend no longer depends on `localStorage` for auth state.
```

4. Cover regression and integration concerns.
```text
- Verify existing moderator Basic Auth still works.
- Verify verification and reset codes are never logged or returned in API responses.
- Verify the frontend and backend remain compatible with the future Redis migration points.
```

5. Prepare rollout and sign-off.
```text
- Review required environment variables for CORS, cookies, SMTP, and frontend API base URL.
- Call out that sessions and throttling are in-memory for MVP unless Redis-backed work is implemented separately.
- Check all items from the specification Definition of Done before release.
```

## Validation

- Execute the full checklist from the specification and record pass/fail status for each scenario.
- Confirm rollout documentation includes required environment variables and MVP limitations.
- Confirm release sign-off includes backend, frontend, security, and regression coverage rather than only endpoint happy paths.
