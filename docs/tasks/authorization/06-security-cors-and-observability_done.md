# Task: Security, CORS, and Observability

- Objective: Capture the cross-cutting security, credential-delivery, logging, and migration requirements around the authorization feature.
- Owner: Dev
- Dependencies: `01-auth-foundation-and-config_done.md`, `02-session-auth-api_done.md`, `03-email-verification_done.md`, `04-password-reset_done.md`, `05-frontend-auth-flow_done.md`
- Success Criteria:
  - CORS is configured with explicit origins and `allow_credentials=True`.
  - Cookies follow the specified `HttpOnly`, `SameSite`, `Secure`, and `Path=/` contract.
  - Password policy, email normalization, session expiry, and non-leakage rules are enforced server-side.
  - Sensitive values never appear in logs, API responses, or browser storage.
  - Redis migration boundaries and rate-limiting expectations are clearly separated between MVP and post-MVP work.

## Steps

1. Configure credentialed CORS in `web/main.py`.
```text
- Add `CORSMiddleware` with an explicit frontend origin.
- Enable `allow_credentials=True`.
- Avoid wildcard origins because cookies must be sent cross-origin.
```

2. Enforce password and identity safety rules.
```text
- Normalize and trim emails before persistence and lookup.
- Enforce password length and composition on the server side.
- Generate a fresh `session_id` on every login and registration.
- Check session expiry on every request that uses the auth cookie.
```

3. Apply cookie and response hardening.
```text
- Set the auth cookie as `HttpOnly`.
- Keep `SameSite` and `Secure` driven by configuration.
- Return generic login failures and neutral password-reset responses to reduce user enumeration risk.
- Avoid exposing password hashes, verification codes, or reset codes anywhere in API payloads.
```

4. Add safe logging expectations.
```text
- Log auth and email-service failures with enough context to debug the issue.
- Do not downgrade real failures to silent warnings.
- Catch only expected exceptions, log with context, and re-raise where appropriate.
- Keep one-time codes and secrets out of logs.
```

5. Isolate future Redis work without hiding MVP limits.
```text
- Keep repository and helper boundaries suitable for Redis-backed session storage.
- Keep attempt counters in MVP where specified.
- Document that distributed rate limiting and audit logging are post-MVP hardening tasks, not hidden fallback behavior.
```

## Validation

- Verify the frontend can send and receive auth cookies with the configured origin and credentials settings.
- Inspect auth and email-service logs to confirm no passwords, hashes, or one-time codes are written.
- Confirm generic and neutral responses are used where the specification requires anti-enumeration behavior.
- Review the implementation boundary to ensure swapping in Redis does not require changing endpoint contracts.
