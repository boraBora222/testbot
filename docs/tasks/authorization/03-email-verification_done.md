# ~~Task: Email Verification~~

- Objective: Implement the email verification flow with one-time codes, expiry checks, attempt limits, and SMTP delivery.
- Owner: Dev
- Dependencies: `01-auth-foundation-and-config_done.md`, `02-session-auth-api_done.md`, SMTP credentials and sender configuration
- Success Criteria:
  - `web/services/email_service.py` sends verification messages without exposing sensitive data in logs.
  - `POST /auth/send-verification-code` stores only the hashed code and expiry.
  - `POST /auth/verify-email` validates hash, expiry, and attempt limits before marking the user as verified.
  - The API does not leak verification codes or internal verification state in responses.
  - Verification can be completed without creating a new session.

## Steps

1. Create the email service in `web/services/email_service.py`.
```text
- Add `send_verification_code(email: str, code: str) -> None`.
- Load SMTP configuration from `web/config.py`.
- Log only delivery context and failures; never log the one-time code itself.
- Keep the email layer separate from auth business logic.
```

2. Add verification-code lifecycle helpers.
```text
- Generate a numeric one-time code of configured length.
- Hash the code before storing it in the repository.
- Store expiry and reset the attempt counter when a new code is issued.
```

3. Implement `POST /auth/send-verification-code`.
```text
- Accept a normalized email address.
- Return a neutral success response when the user does not exist.
- Return a neutral success response when the email is already verified.
- For an eligible user, store the hashed code and expiry, then dispatch the email.
- Leave room for resend throttling and later Redis-backed rate limiting.
```

4. Implement `POST /auth/verify-email`.
```text
- Accept `email` and `code`.
- Reject malformed or expired codes.
- Compare only the hashed form of the submitted code.
- Increment attempt counters on failure and block after the configured threshold.
- Mark `email_verified = true` and clear verification metadata on success.
```

5. Define UX and backend boundary rules.
```text
- Do not auto-login or rotate sessions during verification.
- Keep verification status visible in auth responses so the frontend can prompt the user.
- Never expose whether the code hash is present or absent in a way that leaks internal state.
```

## Validation

- Register or prepare an unverified user, send a code, and verify that the code metadata is stored as a hash only.
- Verify email with a valid code and confirm the user becomes verified and verification metadata is cleared.
- Submit invalid and expired codes and confirm attempt counters and failure responses behave as specified.
- Exceed the maximum allowed attempts and confirm further verification is blocked until a new code is requested.
- Review logs to confirm the plain verification code never appears.
