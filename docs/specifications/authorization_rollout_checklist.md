# Authorization Rollout Checklist

This document turns the authorization specification into a release-facing verification matrix for backend, frontend, security, and rollout readiness.

## Backend Verification Matrix

| Scenario | Expected Result | Coverage |
| --- | --- | --- |
| `POST /auth/register` success | User is created, email is normalized, and a fresh auth cookie is issued | Automated |
| `POST /auth/login` success | Valid credentials create a fresh session and return the authenticated user payload | Automated |
| `POST /auth/logout` success | Current session is deleted and the auth cookie is cleared | Automated |
| `GET /auth/me` with valid cookie | Auth state is restored from the backend session only | Automated |
| `GET /auth/me` with missing cookie | Request fails with `401 Authentication required.` | Automated |
| `GET /auth/me` with invalid cookie | Request fails with `401 Authentication required.` | Automated |
| `GET /auth/me` with expired session | Request fails with `401 Authentication required.` and the expired session is removed | Automated |
| Duplicate registration | Request fails with `409` and does not create a second user | Automated |
| Invalid email input | Request fails validation and does not create a user | Automated |
| Weak password input | Request fails with a server-side password policy error | Automated |
| Generic login failure | Unknown email and wrong password both return the same generic error | Automated |
| Verification request for missing account | Response stays neutral and does not leak account existence | Automated |
| Verification confirmation with invalid code | Request fails without exposing internal code state | Automated |
| Verification confirmation with expired code | Request fails and counts against the configured attempt limit | Automated |
| Verification confirmation over attempt limit | Request fails with `429` and requires a new code | Automated |
| Password reset request for missing account | Response stays neutral and does not leak account existence | Automated |
| Password reset with invalid code | Request fails without exposing internal code state | Automated |
| Password reset with expired code | Request fails with the documented expired-code response | Automated |
| Password reset over attempt limit | Request fails with `429` and requires a new code | Automated |
| Password reset success | Password hash is replaced, reset code is cleared, and all existing sessions are invalidated | Automated |
| Login after password reset | Old password fails and the new password succeeds | Automated |

## Frontend Verification Matrix

| Scenario | Expected Result | Coverage |
| --- | --- | --- |
| Auth bootstrap on app mount | Frontend restores auth state only via `GET /auth/me` | Manual |
| Protected routes | Unauthenticated users are redirected to the login screen | Manual |
| Login page | Sends credentialed requests and applies backend validation messages | Manual |
| Register page | Sends credentialed requests and relies on backend response payloads | Manual |
| Verify email page | Uses the neutral request flow and the code confirmation contract | Manual |
| Forgot password page | Uses the neutral reset-request contract | Manual |
| Reset password page | Uses the reset confirmation contract and does not store secrets locally | Manual |
| Browser storage review | No auth state, passwords, or one-time codes are stored in `localStorage` | Manual |

## Security and Regression Checks

| Check | Expected Result | Coverage |
| --- | --- | --- |
| CORS preflight | `Access-Control-Allow-Origin` matches `FRONT_BASE_URL` and `Access-Control-Allow-Credentials` is `true` | Automated |
| Cookie contract | Auth cookie is `HttpOnly`, uses configured `SameSite`, respects `Secure`, and keeps `Path=/` | Automated |
| Sensitive logging | Passwords, password hashes, verification codes, reset codes, and raw session identifiers never appear in logs | Automated + Review |
| API payload hardening | Verification and reset endpoints never return one-time codes or password material | Automated + Review |
| Moderator Basic Auth | Existing moderator docs access continues to work | Automated |
| Redis migration boundary | Session and code-attempt helpers remain isolated behind repository/helper functions | Review |

## Environment Readiness

Release validation must confirm the following variables are set correctly before rollout:

| Variable | Purpose |
| --- | --- |
| `FRONT_BASE_URL` | Explicit credentialed CORS origin for frontend requests |
| `WEB_BASE_URL` | Canonical backend/web base URL used by the service |
| `AUTH_COOKIE_NAME` | Auth cookie name shared by backend and browser |
| `AUTH_COOKIE_SECURE` | Enables `Secure` cookies in HTTPS environments |
| `AUTH_COOKIE_SAMESITE` | Controls cross-site cookie behavior |
| `AUTH_SESSION_TTL_HOURS` | Session lifetime enforced server-side |
| `AUTH_PASSWORD_MIN_LENGTH` | Minimum password length policy |
| `AUTH_VERIFICATION_CODE_TTL_MINUTES` | Email verification code lifetime |
| `AUTH_RESET_CODE_TTL_MINUTES` | Password reset code lifetime |
| `AUTH_VERIFICATION_CODE_LENGTH` | Verification code length |
| `AUTH_RESET_CODE_LENGTH` | Reset code length |
| `AUTH_MAX_CODE_ATTEMPTS` | Max attempts per active verification/reset code |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP server port |
| `SMTP_USERNAME` | SMTP authentication username |
| `SMTP_PASSWORD` | SMTP authentication password |
| `SMTP_FROM_EMAIL` | Sender address for verification and reset emails |
| `SMTP_USE_TLS` | SMTP TLS toggle |
| `VITE_API_BASE_URL` | Frontend API base URL used by auth requests |

## MVP Rollout Limitations

- Session storage is still in-memory for MVP. A restart clears active sessions.
- Verification and password-reset attempt counters are still in-memory for MVP.
- Redis-backed distributed rate limiting is a planned post-MVP hardening step and is not silently enabled here.
- Audit logging with IP and user-agent enrichment is also post-MVP work.
- No hidden fallback auth storage, retry loop, or alternate credential transport should be introduced during rollout.

## Release Sign-Off

The release can be signed off only when all items below are true:

1. The backend automated auth suite passes.
2. Frontend credentialed auth flows are manually verified against the live backend.
3. Moderator Basic Auth regression is checked.
4. CORS and cookie behavior are validated in the target environment.
5. SMTP delivery works without logging secrets or one-time codes.
6. The Definition of Done from `docs/specifications/authorization.md` is fully satisfied.
