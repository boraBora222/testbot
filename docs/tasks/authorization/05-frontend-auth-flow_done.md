# Task: Frontend Auth Flow

- Objective: Replace mock and browser-storage-based auth with a backend-driven session flow powered by `/auth/me`.
- Owner: Dev
- Dependencies: `02-session-auth-api_done.md`, `03-email-verification_done.md`, `04-password-reset_done.md`, frontend routing setup
- Success Criteria:
  - `front/src/config/service.ts` exposes all auth methods and sends requests with `credentials: "include"`.
  - `front/src/contexts/AuthContext.tsx` initializes auth state from `/auth/me` on app mount.
  - Login, register, verify-email, forgot-password, and reset-password pages are wired to the new API contract.
  - `ProtectedRoute` relies only on `AuthContext` state and no longer reads `localStorage`.
  - All `localStorage`, `mockUser`, and equivalent mock auth assumptions are removed from the auth flow.

## Steps

1. Update the frontend service layer in `front/src/config/service.ts`.
```text
- Add `register`, `login`, `logout`, `me`, `sendVerificationCode`,
  `verifyEmail`, `requestPasswordReset`, and `resetPassword`.
- Send every auth-related request with `credentials: "include"`.
- Keep response types aligned with the backend `AuthUserResponse` and simple success payloads.
```

2. Refactor `front/src/contexts/AuthContext.tsx`.
```text
- Load the current user from `/auth/me` when the app mounts.
- Expose `user`, `isLoading`, `isAuthenticated`, and auth action methods.
- Replace local mock restoration logic with backend-driven session restoration.
- Make logout clear client state only after the API call completes.
```

3. Implement or update auth pages.
```text
- Login page: email, password, login action, links to register and forgot-password.
- Register page: email, password, confirm-password, register action, and post-register verification prompt.
- Verify-email page: email, code, verify action, resend-code action.
- Forgot-password page: email and request-reset action.
- Reset-password page: email, code, new password, confirm password, submit action.
```

4. Update route protection and auth UX.
```text
- Refactor `front/src/components/auth/ProtectedRoute.tsx` to use only context state.
- Render a loading placeholder while auth state is being resolved from `/auth/me`.
- Redirect unauthenticated users to login.
- Preserve room for future route-level enforcement of `email_verified`.
```

5. Remove legacy auth shortcuts.
```text
- Remove `localStorage` auth flags and mock user hydration.
- Replace any direct client-only auth checks with context values derived from backend state.
- Keep only UI-level defaults where harmless; do not invent business-state fallbacks.
```

## Validation

- Reload the application with a valid cookie and confirm auth state is restored through `/auth/me`, not browser storage.
- Clear cookies and confirm protected routes redirect to login after the loading state completes.
- Complete the login, register, verify-email, forgot-password, and reset-password flows against the backend.
- Search the frontend for `localStorage` and `mockUser` usage and confirm auth flow dependencies are removed.
