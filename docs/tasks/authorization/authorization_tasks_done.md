### Authorization implementation - task breakdown

This document breaks the authorization specification into concrete implementation tasks for this repository.

---

### 1. Foundation and configuration

- **Task 1.1 - Add auth domain models**
  - Define `WebUserDB` and `AuthSessionDB` in `shared/models.py`.
  - Include fields required for session auth, email verification, password reset, timestamps, and activation flags.

- **Task 1.2 - Add auth repository functions**
  - Extend `shared/db.py` with in-memory repository functions for web users, sessions, verification codes, reset codes, and session invalidation.
  - Keep function signatures stable so the storage layer can be swapped to Redis later.

- **Task 1.3 - Add auth and SMTP configuration**
  - Extend `web/config.py` with cookie, session TTL, password policy, verification/reset code, and SMTP settings.
  - Map values to the environment variables defined in the specification.

- **Task 1.4 - Add API schemas for auth**
  - Extend `web/models.py` with request and response models for all auth endpoints.
  - Centralize server-side email normalization and input validation boundaries.

- **Task 1.5 - Preserve moderator auth separation**
  - Document and verify that the existing moderator Basic Auth path in `web/auth.py` remains unchanged.
  - Keep user session auth isolated as a separate router and dependency flow.

---

### 2. Session-based auth API

- **Task 2.1 - Add auth helper functions**
  - Implement password hashing and verification with Argon2id.
  - Add helpers for one-time code generation, one-time code hashing, cookie set/clear, and current-user resolution from the session cookie.

- **Task 2.2 - Implement `POST /auth/register`**
  - Validate email and password rules.
  - Reject duplicate email registrations case-insensitively.
  - Create the user, create a fresh session, set the auth cookie, and return the authenticated user payload.

- **Task 2.3 - Implement `POST /auth/login`**
  - Validate credentials with a generic invalid-credentials response.
  - Create a fresh session on every successful login and update `last_login_at`.

- **Task 2.4 - Implement `POST /auth/logout` and `GET /auth/me`**
  - Delete the session identified by the cookie and always clear the auth cookie on logout.
  - Resolve the current authenticated user from the cookie and return `401` when the session is absent, invalid, or expired.

---

### 3. Email verification

- **Task 3.1 - Build the email delivery service**
  - Create `web/services/email_service.py` with SMTP-backed helpers for verification and reset messages.
  - Ensure logs stay production-safe and never expose one-time codes.

- **Task 3.2 - Implement `POST /auth/send-verification-code`**
  - Accept `email`, respond neutrally when the user does not exist or is already verified, and store only the code hash and expiry.
  - Prepare the handler for resend throttling and future rate limiting.

- **Task 3.3 - Implement `POST /auth/verify-email`**
  - Validate code hash, expiry, and attempt limits.
  - Mark the user as verified on success and clear verification metadata.
  - Increment attempts and block further verification after the configured threshold until a new code is requested.

---

### 4. Password reset

- **Task 4.1 - Implement `POST /auth/request-password-reset`**
  - Accept `email`, always return a neutral success response, and store only the hashed reset code with its expiry.
  - Use the email service without leaking whether the account exists.

- **Task 4.2 - Implement `POST /auth/reset-password`**
  - Validate the reset code, password policy, and confirmation match.
  - Replace the stored password hash, clear reset metadata, and invalidate all active sessions for the user.
  - Do not auto-login the user after password reset.

---

### 5. Frontend auth flow

- **Task 5.1 - Update the frontend API client**
  - Extend `front/src/config/service.ts` with methods for register, login, logout, me, verification, and reset flows.
  - Send all auth requests with `credentials: "include"`.

- **Task 5.2 - Rebuild auth state around `/auth/me`**
  - Refactor `front/src/contexts/AuthContext.tsx` so auth state is initialized from the backend on app mount.
  - Remove all dependency on `localStorage` and mock user data for auth state.

- **Task 5.3 - Implement auth pages**
  - Update or create pages for login, register, verify email, forgot password, and reset password.
  - Ensure the UI reflects `email_verified` and the backend response contract.

- **Task 5.4 - Update route protection**
  - Refactor `front/src/components/auth/ProtectedRoute.tsx` to rely only on `AuthContext`.
  - Handle loading, unauthenticated redirects, and authenticated rendering consistently.

---

### 6. Security, CORS, and observability

- **Task 6.1 - Add CORS support for credentialed auth**
  - Configure `web/main.py` with explicit origins and `allow_credentials=True`.
  - Ensure auth cookies can be delivered cross-origin without wildcard origins.

- **Task 6.2 - Enforce the security checklist**
  - Apply the password policy, email normalization, cookie security settings, and non-leakage rules from the specification.
  - Ensure passwords, password hashes, and one-time codes never appear in responses, logs, or browser storage.

- **Task 6.3 - Isolate migration and throttling boundaries**
  - Keep Redis migration points behind repository/service functions.
  - Document the difference between MVP attempt counters and post-MVP Redis-backed distributed rate limiting.

---

### 7. Testing, rollout, and Definition of Done

- **Task 7.1 - Convert the auth checklist into executable verification**
  - Cover register, login, logout, me, duplicate registration, validation, and moderator auth regression.
  - Add verification and password reset success and failure scenarios, including expired codes and session invalidation after reset.

- **Task 7.2 - Validate frontend auth behavior**
  - Confirm the frontend no longer depends on `localStorage`.
  - Verify protected routes redirect unauthenticated users and render correctly after session restoration via `/auth/me`.

- **Task 7.3 - Prepare rollout and environment readiness**
  - Verify required environment variables for CORS, cookies, SMTP, and frontend API base URL.
  - Document in-memory limitations and the Redis migration path for later production hardening.

- **Task 7.4 - Confirm Definition of Done**
  - Check the completed work against the specification DoD, including backend flows, frontend state, security requirements, and test coverage.
