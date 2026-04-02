Ниже — цельная обновлённая версия ТЗ, собранная на основе исходного плана session-based авторизации с HttpOnly cookies, 4 базовых auth endpoint’ов, Security Checklist, Post-MVP и environment variables, куда я включил подтверждение email и сброс пароля в основной scope, а не в отложенные улучшения.

# Final Design Plan: Secure Session-Based User Authentication System

## 1. Executive Summary & Goals

**Primary Objective:** Replace mock/localStorage frontend authentication with production-ready session-based email/password authentication using HttpOnly cookies and Argon2id password hashing, while preserving existing moderator basic auth and establishing a clear migration path to Redis-backed sessions.

**Key Goals:**

1. Implement 8 auth endpoints (`/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/send-verification-code`, `/auth/verify-email`, `/auth/request-password-reset`, `/auth/reset-password`) with server-side session management via HttpOnly cookies.
2. Establish a DB-agnostic data access layer with in-memory implementation, pre-wired for Redis session storage in production.
3. Eliminate all `localStorage`/`mockUser` usage; make frontend auth state entirely server-driven via `/auth/me`.
4. Add CORS middleware with credentials support for cross-origin cookie delivery.
5. Design a separate `/users/profile` endpoint for extended user data (phone, telegram, whitelist, API keys) to keep auth lean.
6. Define Redis-based rate limiting pattern for production brute-force protection.
7. Add email verification flow via one-time verification code with TTL and attempt limits.
8. Add password reset flow via one-time reset code with TTL, secure confirmation, and password hash replacement.

---

## 2. Current Situation Analysis

| Area               | Current State                    | Target State                                                                                                               |
| ------------------ | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Frontend auth      | `localStorage` flag + `mockUser` | Server-driven via `/auth/me`, zero client-side storage                                                                     |
| Password storage   | N/A (mock)                       | Argon2id hash only, never plaintext                                                                                        |
| Session management | None                             | HttpOnly cookie, TTL-based expiry, in-memory → Redis migration path                                                        |
| Moderator auth     | HTTP Basic Auth in `web/auth.py` | **Unchanged** — user auth is separate router                                                                               |
| CORS               | Not configured                   | `allow_credentials=True`, explicit `allow_origins`                                                                         |
| Data layer         | MongoDB-specific (motor)         | New auth functions with identical signatures for future Redis swap                                                         |
| User profile data  | Embedded in mock `User` type     | Separate `/users/profile` endpoint (post-MVP)                                                                              |
| Email verification | Not implemented                  | One-time verification code sent to email, code hash stored server-side, user marked verified after successful confirmation |
| Password reset     | Not implemented                  | One-time password reset code sent to email, reset allowed only with valid unexpired code                                   |

---

## 3. Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React/TS)                          │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  LoginPage   │    │ RegisterPage │    │   ProtectedRoute     │  │
│  └──────┬───────┘    └──────┬───────┘    └──────────┬───────────┘  │
│         │                   │                        │              │
│  ┌──────▼───────┐    ┌──────▼────────┐    ┌─────────▼────────┐     │
│  │ VerifyEmail  │    │ ForgotPassword│    │  ResetPassword   │     │
│  └──────┬───────┘    └──────┬────────┘    └─────────┬────────┘     │
│         └───────────────────┼────────────────────────┘              │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │  AuthContext    │ ◄── calls /auth/me on mount  │
│                    │  (no localStorage)                             │
│                    └────────┬────────┘                              │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │ service.ts      │ ◄── credentials: "include"   │
│                    │ (register,      │                              │
│                    │  login, logout, │                              │
│                    │  me,            │                              │
│                    │  sendVerificationCode,                         │
│                    │  verifyEmail,                                  │
│                    │  requestPasswordReset,                         │
│                    │  resetPassword)                                │
│                    └────────┬────────┘                              │
└─────────────────────────────┼───────────────────────────────────────┘
                              │ HTTP + HttpOnly Cookie
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    web/main.py                              │   │
│  │  - CORSMiddleware (allow_credentials=True)                  │   │
│  │  - app.include_router(auth_router)  ◄── NEW                 │   │
│  │  - app.include_router(applications.router)  ◄── EXISTING    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    web/auth.py                              │   │
│  │  ┌─────────────────────┐  ┌─────────────────────────────┐  │   │
│  │  │ Moderator Basic Auth│  │ User Session Auth (NEW)     │  │   │
│  │  │ (unchanged)         │  │ - hash_password()           │  │   │
│  │  │ - authenticate_     │  │ - verify_password()         │  │   │
│  │  │   moderator()       │  │ - get_current_user()        │  │   │
│  │  └─────────────────────┘  │ - POST /auth/register       │  │   │
│  │                           │ - POST /auth/login          │  │   │
│  │                           │ - POST /auth/logout         │  │   │
│  │                           │ - GET  /auth/me             │  │   │
│  │                           │ - POST /auth/send-          │  │   │
│  │                           │   verification-code         │  │   │
│  │                           │ - POST /auth/verify-email   │  │   │
│  │                           │ - POST /auth/request-       │  │   │
│  │                           │   password-reset            │  │   │
│  │                           │ - POST /auth/reset-password │  │   │
│  │                           └─────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              shared/models.py (NEW MODELS)                  │   │
│  │  WebUserDB (id, email, password_hash, is_active,            │   │
│  │             email_verified, name, company, created_at,      │   │
│  │             updated_at, last_login_at,                      │   │
│  │             verification/reset code metadata)               │   │
│  │  AuthSessionDB (session_id, user_id, created_at,            │   │
│  │                 expires_at)                                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              shared/db.py (NEW FUNCTIONS)                   │   │
│  │  In-memory dicts: _web_users, _auth_sessions                │   │
│  │  Functions: create/get user, update last login,             │   │
│  │             create/get/delete session,                      │   │
│  │             set/clear verification code,                    │   │
│  │             set/clear reset code,                           │   │
│  │             update password hash,                           │   │
│  │             delete all user sessions                        │   │
│  │  TODO comments mark Redis migration points                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │          web/services/email_service.py (NEW)                │   │
│  │  - send_verification_code()                                 │   │
│  │  - send_password_reset_code()                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              web/redis_client.py (EXTENDED)                 │   │
│  │  Future: rate limiting helpers for auth endpoints           │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Session Flow:**

1. Client submits credentials to `/auth/login` or `/auth/register`.
2. Server validates, hashes/verifies password, creates session record.
3. Server sets `Set-Cookie: <auth_cookie_name>=<session_id>; HttpOnly; SameSite=Lax; Secure=<config>; Path=/`.
4. Browser automatically includes cookie on subsequent requests.
5. `/auth/me` reads cookie, looks up session, returns user data or 401.
6. `/auth/logout` deletes session, clears cookie.

**Email Verification Flow:**

1. User registers or requests verification code resend.
2. Server generates a 6-digit one-time code, stores only its hash and expiry timestamp.
3. Code is sent to the user email.
4. User submits email + code to `/auth/verify-email`.
5. Server verifies hash, expiry, and attempt limit.
6. On success, `email_verified = true`, verification code fields are cleared.

**Password Reset Flow:**

1. User submits email to `/auth/request-password-reset`.
2. Server generates a 6-digit one-time reset code, stores only its hash and expiry timestamp.
3. Code is sent to the user email.
4. User submits email + code + new password + confirm password to `/auth/reset-password`.
5. Server validates code, expiry, password policy, and confirmation match.
6. On success, password hash is replaced, reset code fields are cleared, and all previous auth sessions for the user are invalidated.

---

## 4. File-by-File Implementation

### 4.1. `shared/models.py` — New Data Models

Add at end of file:

```python
class WebUserDB(BaseModel):
    """Website user document for email/password authentication."""
    id: str
    email: str
    password_hash: str
    is_active: bool = True
    email_verified: bool = False
    name: str = ""
    company: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None

    email_verification_code_hash: Optional[str] = None
    email_verification_code_expires_at: Optional[datetime] = None
    email_verification_attempts: int = 0

    password_reset_code_hash: Optional[str] = None
    password_reset_code_expires_at: Optional[datetime] = None
    password_reset_attempts: int = 0

    class Config:
        populate_by_name = True


class AuthSessionDB(BaseModel):
    """Authentication session document for session-based auth."""
    session_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    class Config:
        populate_by_name = True
```

### 4.2. `shared/db.py` — In-Memory Repository Layer

Update imports:

```python
from shared.models import (
    # ... existing imports ...
    WebUserDB,
    AuthSessionDB,
)
```

Add at end of file:

```python
# =============================================================================
# Web User Auth — In-memory storage (temporary, replace with Redis later)
# =============================================================================

_web_users: dict[str, WebUserDB] = {}
_auth_sessions: dict[str, AuthSessionDB] = {}


async def create_web_user(user: WebUserDB) -> WebUserDB:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    _web_users[user.email] = user
    return user


async def get_web_user_by_email(email: str) -> Optional[WebUserDB]:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    return _web_users.get(email.lower())


async def get_web_user_by_id(user_id: str) -> Optional[WebUserDB]:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            return user
    return None


async def update_web_user_last_login(user_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    now = _utc_now()
    for user in _web_users.values():
        if user.id == user_id:
            user.last_login_at = now
            user.updated_at = now
            break


async def create_auth_session(session: AuthSessionDB) -> AuthSessionDB:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    _auth_sessions[session.session_id] = session
    return session


async def get_auth_session(session_id: str) -> Optional[AuthSessionDB]:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    session = _auth_sessions.get(session_id)
    if session and session.expires_at > datetime.now(timezone.utc):
        return session
    return None


async def delete_auth_session(session_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    _auth_sessions.pop(session_id, None)


async def delete_auth_sessions_for_user(user_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    session_ids = [sid for sid, session in _auth_sessions.items() if session.user_id == user_id]
    for sid in session_ids:
        _auth_sessions.pop(sid, None)


async def set_email_verification_code(
    user_id: str,
    code_hash: str,
    expires_at: datetime,
) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verification_code_hash = code_hash
            user.email_verification_code_expires_at = expires_at
            user.email_verification_attempts = 0
            user.updated_at = _utc_now()
            break


async def increment_email_verification_attempts(user_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verification_attempts += 1
            user.updated_at = _utc_now()
            break


async def clear_email_verification_code(user_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verification_code_hash = None
            user.email_verification_code_expires_at = None
            user.email_verification_attempts = 0
            user.updated_at = _utc_now()
            break


async def mark_web_user_email_verified(user_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.email_verified = True
            user.email_verification_code_hash = None
            user.email_verification_code_expires_at = None
            user.email_verification_attempts = 0
            user.updated_at = _utc_now()
            break


async def set_password_reset_code(
    user_id: str,
    code_hash: str,
    expires_at: datetime,
) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.password_reset_code_hash = code_hash
            user.password_reset_code_expires_at = expires_at
            user.password_reset_attempts = 0
            user.updated_at = _utc_now()
            break


async def increment_password_reset_attempts(user_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.password_reset_attempts += 1
            user.updated_at = _utc_now()
            break


async def clear_password_reset_code(user_id: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.password_reset_code_hash = None
            user.password_reset_code_expires_at = None
            user.password_reset_attempts = 0
            user.updated_at = _utc_now()
            break


async def update_web_user_password_hash(user_id: str, password_hash: str) -> None:
    # TODO: Replace with actual DB query when migrating from in-memory storage
    for user in _web_users.values():
        if user.id == user_id:
            user.password_hash = password_hash
            user.updated_at = _utc_now()
            break
```

### 4.3. `web/config.py` — Auth Configuration

Add to `WebSettings` class:

```python
# Auth settings
auth_cookie_name: str = "cryptodeal_session"
auth_session_ttl_hours: int = 24
auth_cookie_secure: bool = False
auth_cookie_samesite: str = "lax"
auth_password_min_length: int = 8

auth_verification_code_ttl_minutes: int = 10
auth_reset_code_ttl_minutes: int = 10
auth_verification_code_length: int = 6
auth_reset_code_length: int = 6
auth_max_code_attempts: int = 5

smtp_host: str = ""
smtp_port: int = 587
smtp_username: str = ""
smtp_password: str = ""
smtp_from_email: str = ""
smtp_use_tls: bool = True
```

### 4.4. `web/models.py` — API Request/Response Schemas

Add at end of file:

```python
import re
from pydantic import BaseModel, field_validator

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class RegisterRequest(BaseModel):
    email: str
    password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_REGEX.match(value):
            raise ValueError("Invalid email format")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_REGEX.match(value):
            raise ValueError("Invalid email format")
        return value


class SendVerificationCodeRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_REGEX.match(value):
            raise ValueError("Invalid email format")
        return value


class VerifyEmailRequest(BaseModel):
    email: str
    code: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_REGEX.match(value):
            raise ValueError("Invalid email format")
        return value


class RequestPasswordResetRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_REGEX.match(value):
            raise ValueError("Invalid email format")
        return value


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_REGEX.match(value):
            raise ValueError("Invalid email format")
        return value


class AuthUserResponse(BaseModel):
    id: str
    email: str
    email_verified: bool
    is_active: bool
    name: str = ""
    company: str = ""


class SimpleSuccessResponse(BaseModel):
    success: bool = True
    message: str
```

### 4.5. `web/auth.py` — User Session Auth

Add:

* `hash_password(password: str) -> str`
* `verify_password(password: str, hash: str) -> bool`
* `generate_one_time_code(length: int) -> str`
* `hash_one_time_code(code: str) -> str`
* `set_auth_cookie(response, session_id)`
* `clear_auth_cookie(response)`
* `get_current_user(request)`

Implement endpoints:

#### `POST /auth/register`

* Validates email format and password policy.
* Normalizes email to lowercase.
* Rejects duplicates.
* Hashes password with Argon2id.
* Creates `WebUserDB`.
* Creates session.
* Sets auth cookie.
* Returns authenticated user payload.

#### `POST /auth/login`

* Validates credentials.
* Uses generic error message for invalid email or password.
* Updates `last_login_at`.
* Creates fresh session ID.
* Sets auth cookie.
* Returns authenticated user payload including `email_verified`.

#### `POST /auth/logout`

* Deletes session by cookie value.
* Clears auth cookie.
* Returns success response.

#### `GET /auth/me`

* Reads session cookie.
* Loads session and user.
* Returns current authenticated user or 401.

#### `POST /auth/send-verification-code`

* Accepts `email`.
* If user not found, returns `200` with neutral response.
* If email already verified, returns `200` with neutral response.
* Generates one-time 6-digit verification code.
* Stores only hash and expiry.
* Sends code to email.
* May apply resend throttling / rate limiting.

#### `POST /auth/verify-email`

* Accepts `email` and `code`.
* Validates code hash and expiry.
* On success:

  * marks user as verified
  * clears verification code fields
* On failure:

  * increments attempt counter
  * blocks further attempts after configured threshold until new code is requested

#### `POST /auth/request-password-reset`

* Accepts `email`.
* Always returns neutral `200` response regardless of whether user exists.
* Generates one-time reset code.
* Stores only hash and expiry.
* Sends code to email.
* Supports rate limiting.

#### `POST /auth/reset-password`

* Accepts `email`, `code`, `new_password`, `confirm_password`.
* Validates confirmation match and password policy.
* Validates reset code and expiry.
* On success:

  * hashes and updates password
  * clears reset code fields
  * deletes all active sessions for the user
* Does not automatically create a new login session.

#### Business Rules

* Login is allowed even when `email_verified = false`, but verification status is returned in auth responses.
* Protected routes may optionally enforce `email_verified = true` at business level where needed.
* Email verification does not create a new session.
* Password reset does not automatically log in the user.
* Verification/reset codes must never be logged or returned in API responses.

### 4.6. `web/services/email_service.py` — Sending Verification and Reset Codes

Create a small email service with functions:

```python
async def send_verification_code(email: str, code: str) -> None: ...
async def send_password_reset_code(email: str, code: str) -> None: ...
```

Requirements:

* SMTP-based implementation
* configurable via environment variables
* clear separation from auth business logic
* production-safe logging without exposing codes

### 4.7. `front/src/config/service.ts` — Frontend API Layer

Add methods:

```typescript
async register(email: string, password: string, confirmPassword: string): Promise<AuthUser> { ... }
async login(email: string, password: string): Promise<AuthUser> { ... }
async logout(): Promise<void> { ... }
async me(): Promise<AuthUser | null> { ... }

async sendVerificationCode(email: string): Promise<{ success: boolean; message: string }> { ... }
async verifyEmail(email: string, code: string): Promise<{ success: boolean; message: string }> { ... }
async requestPasswordReset(email: string): Promise<{ success: boolean; message: string }> { ... }
async resetPassword(
  email: string,
  code: string,
  newPassword: string,
  confirmPassword: string
): Promise<{ success: boolean; message: string }> { ... }
```

All requests must use:

```typescript
credentials: "include"
```

### 4.8. `front/src/contexts/AuthContext.tsx` — Auth State Management

Auth state must be initialized by `/auth/me` on app mount and never from `localStorage`.

Context API should expose:

```typescript
type AuthContextValue = {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  register: (email: string, password: string, confirmPassword: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;

  sendVerificationCode: (email: string) => Promise<string>;
  verifyEmail: (email: string, code: string) => Promise<string>;
  requestPasswordReset: (email: string) => Promise<string>;
  resetPassword: (
    email: string,
    code: string,
    newPassword: string,
    confirmPassword: string
  ) => Promise<string>;
};
```

### 4.9. Frontend Pages

#### `front/src/pages/login/index.tsx`

* email field
* password field
* login button
* link to register
* link to forgot password

#### `front/src/pages/register/index.tsx`

* email field
* password field
* confirm password field
* register button
* after successful registration:

  * authenticated session is established
  * user sees email verification prompt if `email_verified = false`

#### `front/src/pages/verify-email/index.tsx`

* email field
* verification code field
* button `Подтвердить email`
* button `Отправить код повторно`

#### `front/src/pages/forgot-password/index.tsx`

* email field
* button `Отправить код для сброса`

#### `front/src/pages/reset-password/index.tsx`

* email field
* reset code field
* new password field
* confirm password field
* button `Сбросить пароль`

### 4.10. `front/src/components/auth/ProtectedRoute.tsx`

Must rely only on `AuthContext` state loaded from `/auth/me`.

Behavior:

* while auth state is loading, render loader or placeholder
* if unauthenticated, redirect to login
* if authenticated, render protected content
* optional future extension: require verified email for selected routes

---

## 5. Validation Rules

### Email Rules

* Normalize to lowercase
* Trim surrounding spaces
* Validate format server-side
* Enforce uniqueness case-insensitively

### Password Policy

* Minimum length: `AUTH_PASSWORD_MIN_LENGTH`
* At least one letter
* At least one digit
* `password == confirm_password` required where applicable

### Verification / Reset Code Policy

* Code length: 6 digits
* TTL: 10 minutes, configurable
* Max attempts: 5, configurable
* Codes are stored only as hashes
* Codes are single-use
* Codes must be deleted after successful verification/reset

---

## 6. Testing & Validation

1. Test register success path.
2. Test login success path.
3. Test logout success path.
4. Test `/auth/me` with valid session cookie.
5. Test `/auth/me` without cookie or with invalid/expired session.
6. Test duplicate registration rejection.
7. Test invalid email validation.
8. Test weak password rejection.
9. Test moderator basic auth remains unchanged.
10. Test frontend no longer depends on `localStorage` for auth state.
11. Test protected routes redirect unauthenticated users.
12. Test email verification flow: register → send code → verify email with valid code.
13. Test invalid verification code handling and attempt limits.
14. Test expired verification code handling.
15. Test password reset flow: request reset → submit valid code → login with new password.
16. Test invalid reset code handling.
17. Test expired reset code handling.
18. Verify old password no longer works after reset.
19. Verify new password works after reset.
20. Verify all previous sessions are invalidated after password reset.
21. Verify API responses for verification/reset do not leak whether email exists.
22. Verify codes are never logged or returned in API responses.
23. Verify resend/reset flows are compatible with future Redis rate limiting.

---

## 7. API Specification

| Method | Path                           | Auth Required        | Request Body                  | Success Response                           | Errors   |
| ------ | ------------------------------ | -------------------- | ----------------------------- | ------------------------------------------ | -------- |
| POST   | `/auth/register`               | No                   | `RegisterRequest`             | 200 `AuthUserResponse` + Set-Cookie        | 400, 409 |
| POST   | `/auth/login`                  | No                   | `LoginRequest`                | 200 `AuthUserResponse` + Set-Cookie        | 400, 401 |
| POST   | `/auth/logout`                 | Yes/Session optional | none                          | 200 `SimpleSuccessResponse` + Clear-Cookie | 200      |
| GET    | `/auth/me`                     | Yes                  | none                          | 200 `AuthUserResponse`                     | 401      |
| POST   | `/auth/send-verification-code` | No                   | `SendVerificationCodeRequest` | 200 `SimpleSuccessResponse`                | 400, 429 |
| POST   | `/auth/verify-email`           | No                   | `VerifyEmailRequest`          | 200 `SimpleSuccessResponse`                | 400, 429 |
| POST   | `/auth/request-password-reset` | No                   | `RequestPasswordResetRequest` | 200 `SimpleSuccessResponse`                | 400, 429 |
| POST   | `/auth/reset-password`         | No                   | `ResetPasswordRequest`        | 200 `SimpleSuccessResponse`                | 400, 429 |

### Response Shape for Authenticated User

```json
{
  "id": "user_123",
  "email": "user@example.com",
  "email_verified": false,
  "is_active": true,
  "name": "",
  "company": ""
}
```

### Cookie Contract

```text
Set-Cookie: <auth_cookie_name>=<session_id>; HttpOnly; SameSite=Lax; Secure=<config>; Path=/
```

### Error Response Principles

* Use generic login error for invalid credentials.
* Use neutral response for password reset request to avoid user enumeration.
* Verification and reset flows must avoid exposing whether code hashes or internal state exist.
* Validation errors should be explicit only for malformed input, password mismatch, or weak password.

---

## 8. Migration Path: In-Memory → Redis

Current in-memory dicts are replaced with Redis in production. Function signatures remain identical.

**Redis session storage pattern:**

```python
async def get_auth_session(session_id: str) -> Optional[AuthSessionDB]:
    data = await redis_client.get(f"session:{session_id}")
    if not data:
        return None
    session = AuthSessionDB.model_validate_json(data)
    if session.expires_at <= datetime.now(timezone.utc):
        await redis_client.delete(f"session:{session_id}")
        return None
    return session

async def create_auth_session(session: AuthSessionDB) -> AuthSessionDB:
    ttl = int((session.expires_at - session.created_at).total_seconds())
    await redis_client.setex(
        f"session:{session.session_id}",
        ttl,
        session.model_dump_json(),
    )
    return session
```

**Redis rate limiting pattern:**

```python
async def check_rate_limit(identifier: str, max_attempts: int = 5, window_seconds: int = 900) -> bool:
    key = f"rate_limit:auth:{identifier}"
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, window_seconds)
    return current <= max_attempts
```

Suggested usage:

* login attempts by email
* verification code send attempts by email
* verification code confirm attempts by email
* password reset requests by email
* password reset confirmations by email

---

## 9. Security Checklist

| Control                                   | Implementation                                                            |
| ----------------------------------------- | ------------------------------------------------------------------------- |
| Password hashing                          | Argon2id (`time_cost=3`, `memory_cost=65536`, `parallelism=4`, `Type.ID`) |
| Cookie security                           | `HttpOnly=true`, `SameSite=lax`, `Secure` configurable                    |
| User enumeration prevention               | Generic login error and neutral password reset request response           |
| Email uniqueness                          | Case-insensitive, normalized to lowercase                                 |
| Session fixation prevention               | New `session_id` generated on every login/register                        |
| Session expiry                            | Server-side TTL check on every request                                    |
| No sensitive data leakage                 | No password/hash/code in responses, logs, or browser storage              |
| Password complexity                       | Min length + 1 letter + 1 digit enforced server-side                      |
| CORS credentials                          | Explicit origin, no wildcards                                             |
| Email verification code storage           | Hash only, never plaintext                                                |
| Password reset code storage               | Hash only, never plaintext                                                |
| Session invalidation after password reset | All active sessions removed                                               |
| Verification/reset brute-force protection | Attempt counters + Redis rate limiting pattern                            |

---

## 10. Post-MVP Enhancements

| Feature                       | Priority | Description                                                                       |
| ----------------------------- | -------- | --------------------------------------------------------------------------------- |
| Redis rate limiting hardening | High     | Move all auth throttling from in-memory logic to Redis-backed distributed limiter |
| `/users/profile` endpoint     | Medium   | Serve extended user data such as phone, telegram, whitelist, API keys             |
| Audit logging                 | Medium   | Log auth events with IP, user-agent, verification and reset actions               |
| 2FA / MFA                     | Low      | TOTP-based two-factor authentication                                              |
| Email templates               | Low      | HTML/text templates for verification and reset emails                             |
| Resend cooldown UX            | Low      | Better frontend timers and resend state for one-time codes                        |

---

## 11. Environment Variables

| Variable                             | Purpose                                  | Default                 | Required |
| ------------------------------------ | ---------------------------------------- | ----------------------- | -------- |
| `FRONT_BASE_URL`                     | CORS allowed origin                      | —                       | Yes      |
| `AUTH_COOKIE_SECURE`                 | Cookie `Secure` flag                     | `False`                 | No       |
| `AUTH_SESSION_TTL_HOURS`             | Session lifetime                         | `24`                    | No       |
| `AUTH_PASSWORD_MIN_LENGTH`           | Password policy minimum length           | `8`                     | No       |
| `AUTH_VERIFICATION_CODE_TTL_MINUTES` | Email verification code lifetime         | `10`                    | No       |
| `AUTH_RESET_CODE_TTL_MINUTES`        | Password reset code lifetime             | `10`                    | No       |
| `AUTH_VERIFICATION_CODE_LENGTH`      | Verification code length                 | `6`                     | No       |
| `AUTH_RESET_CODE_LENGTH`             | Reset code length                        | `6`                     | No       |
| `AUTH_MAX_CODE_ATTEMPTS`             | Max attempts for verification/reset code | `5`                     | No       |
| `SMTP_HOST`                          | SMTP server host                         | —                       | Yes      |
| `SMTP_PORT`                          | SMTP server port                         | `587`                   | No       |
| `SMTP_USERNAME`                      | SMTP username                            | —                       | Yes      |
| `SMTP_PASSWORD`                      | SMTP password                            | —                       | Yes      |
| `SMTP_FROM_EMAIL`                    | Sender email address                     | —                       | Yes      |
| `SMTP_USE_TLS`                       | Enable TLS for SMTP                      | `True`                  | No       |
| `VITE_API_BASE_URL`                  | Frontend API base URL                    | `http://localhost:8000` | No       |

---

## 12. Definition of Done

The feature is considered complete when:

1. Frontend authentication no longer uses `localStorage` or mock user state.
2. Backend session-based email/password auth works through HttpOnly cookies.
3. `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me` are fully operational.
4. Email verification flow is operational end-to-end with one-time code delivery and confirmation.
5. Password reset flow is operational end-to-end with one-time code delivery and password replacement.
6. Passwords and one-time codes are never stored in plaintext.
7. Existing moderator basic auth continues to work without regression.
8. CORS is configured correctly for credentialed frontend requests.
9. All listed validation and integration tests pass.
10. Redis migration points remain clearly isolated behind repository/service functions.



