# Task: Password Reset

- Objective: Implement the password reset flow with one-time reset codes, secure password replacement, and session invalidation.
- Owner: Dev
- Dependencies: `01-auth-foundation-and-config_done.md`, `02-session-auth-api_done.md`, `03-email-verification_done.md`
- Success Criteria:
  - `POST /auth/request-password-reset` always returns a neutral success response.
  - Reset codes are stored only as hashes with expiry and attempt tracking.
  - `POST /auth/reset-password` enforces password policy and confirmation matching before updating the password hash.
  - All active user sessions are invalidated after a successful password reset.
  - Password reset does not automatically create a new login session.

## Steps

1. Implement `POST /auth/request-password-reset`.
```text
- Accept a normalized email address.
- Always return the same success response regardless of whether the user exists.
- For an existing user, generate a one-time reset code, hash it, store the expiry, and send it via SMTP.
- Keep the endpoint compatible with future rate limiting and resend controls.
```

2. Implement reset-code storage and failure handling.
```text
- Store the reset code hash, expiry, and attempt count on the user record or equivalent repository object.
- Clear old reset metadata when a new reset code is issued.
- Increment attempts only on invalid confirmation attempts.
```

3. Implement `POST /auth/reset-password`.
```text
- Accept `email`, `code`, `new_password`, and `confirm_password`.
- Fail fast when the confirmation does not match or the password policy is violated.
- Validate code hash, code expiry, and attempt limit before updating the password.
- Replace the stored password hash and clear reset metadata on success.
```

4. Invalidate all existing sessions on success.
```text
- Delete all sessions belonging to the user after the password hash is updated.
- Do not create a new authenticated session automatically.
- Ensure old cookies become useless after reset because the server-side sessions are gone.
```

5. Preserve non-leakage behavior.
```text
- Never reveal whether the email exists in the request endpoint.
- Never log or return the plain reset code.
- Keep failure messages specific only for malformed input, password mismatch, weak password, invalid code, or expired code.
```

## Validation

- Request a password reset for an existing email and verify the repository stores only the hashed code plus expiry metadata.
- Request a password reset for a missing email and confirm the response remains neutral.
- Reset the password with a valid code and confirm the new password works while the old password no longer works.
- Confirm all active sessions are invalidated after reset and `/auth/me` fails for old cookies.
- Submit invalid, expired, and over-limit reset attempts and confirm the flow blocks as specified.
