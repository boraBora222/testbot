# ~~Task: Session Auth API~~

- Objective: Implement the core session-based user auth flow with HttpOnly cookies and server-side session lookup.
- Owner: Dev
- Dependencies: `01-auth-foundation-and-config_done.md`, Argon2id dependency, FastAPI request/response primitives
- Success Criteria:
  - `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, and `GET /auth/me` are fully implemented.
  - Every successful register or login creates a fresh session identifier and sets the auth cookie.
  - `/auth/me` becomes the only source of truth for frontend auth state.
  - Session expiry is checked server-side on every authenticated lookup.
  - Invalid credentials return a generic response without leaking whether the email exists.

## Steps

1. Add auth helper functions in `web/auth.py`.
```text
- Implement `hash_password()` and `verify_password()` using Argon2id.
- Add helpers for one-time code generation and hashing if they will be shared across auth flows.
- Add `set_auth_cookie()`, `clear_auth_cookie()`, and `get_current_user()`.
- Use clear, fail-fast validation when required inputs or session state are invalid.
```

2. Implement `POST /auth/register`.
```text
- Normalize the email to lowercase and reject invalid email format.
- Enforce the password policy and `password == confirm_password`.
- Reject duplicate registrations case-insensitively.
- Create the user record, create a session, set the cookie, and return `AuthUserResponse`.
```

3. Implement `POST /auth/login`.
```text
- Look up the user by normalized email.
- Verify the password hash with a generic invalid-credentials message.
- Update `last_login_at`, create a new session, set the cookie, and return the authenticated user payload.
- Allow login even when `email_verified` is false, but return the verification status in the response.
```

4. Implement `POST /auth/logout`.
```text
- Read the current session cookie, delete the session if present, and always clear the cookie.
- Return a stable success response even if the session is already absent.
```

5. Implement `GET /auth/me`.
```text
- Resolve the session from the cookie.
- Load the user from the session record and return `401` when the cookie is missing, invalid, or expired.
- Keep the response lean and limited to auth-relevant user data.
```

6. Align frontend expectations with backend auth state.
```text
- Treat `/auth/me` as the canonical source for auth state restoration.
- Remove the old assumption that browser storage can restore a session locally.
```

## Validation

- Register a new user and confirm the response returns the authenticated user plus a session cookie.
- Login with valid credentials and verify a fresh session is created.
- Login with an invalid email or password and verify the same generic error is returned.
- Call `/auth/me` with a valid, missing, invalid, and expired session to confirm correct behavior.
- Logout and verify the cookie is cleared and the session cannot be used again.
