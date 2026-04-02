# ~~Task: Auth Foundation and Config~~

- Objective: Establish the backend auth data model, repository contract, configuration surface, and request/response schemas required by the authorization specification.
- Owner: Dev
- Dependencies: [Authorization specification](../../specifications/authorization.md), existing `shared/` and `web/` modules
- Success Criteria:
  - `shared/models.py` has a documented place for `WebUserDB` and `AuthSessionDB`.
  - `shared/db.py` covers user lookup, session lifecycle, verification code lifecycle, reset code lifecycle, and invalidation of all sessions for a user.
  - `web/config.py` exposes auth and SMTP settings required by the specification and environment contract.
  - `web/models.py` defines request and response schemas for all auth endpoints with clear validation responsibilities.
  - Existing moderator Basic Auth behavior is explicitly preserved and kept separate from user session auth.

## Steps

1. Add auth domain models in `shared/models.py`.
```text
- Introduce `WebUserDB` with identifiers, normalized email, password hash, activation state,
  email verification fields, password reset fields, and audit-friendly timestamps.
- Introduce `AuthSessionDB` with `session_id`, `user_id`, `created_at`, and `expires_at`.
```

2. Extend the in-memory repository layer in `shared/db.py`.
```text
- Add create/read/update functions for website users.
- Add create/read/delete functions for auth sessions.
- Add helper functions to set, clear, and increment verification/reset metadata.
- Add a function to invalidate all sessions for a specific user.
- Keep signatures simple and storage-agnostic so Redis can replace the implementation later.
```

3. Extend auth-related configuration in `web/config.py`.
```text
- Add cookie settings, session TTL, password policy, verification/reset code settings, and SMTP settings.
- Keep names aligned with the specification and existing `.env` conventions.
- Do not rename existing variables that already map to environment values.
```

4. Add API request and response schemas in `web/models.py`.
```text
- Define models for register, login, send verification code, verify email,
  request password reset, and reset password.
- Define `AuthUserResponse` and a simple success response model.
- Normalize and validate email input server-side.
- Keep malformed-input validation in schema or endpoint validation, not hidden in downstream logic.
```

5. Document router separation and non-goals.
```text
- Keep existing moderator Basic Auth in `web/auth.py` unchanged.
- Introduce user auth as a distinct router and dependency path.
- Leave `/users/profile` out of MVP implementation and keep it as a later task.
```

## Validation

- Review the spec sections for models, config, API schemas, and DoD to ensure every required field has a destination.
- Confirm the repository contract covers all eight auth endpoints and the password-reset session invalidation rule.
- Confirm environment-facing names match the specification instead of inventing fallback business logic.
