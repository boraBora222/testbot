## Frontend Auth Testing and Docker Execution

This document describes the implemented frontend testing stack for authorization flows, the Docker entrypoints used by the team, and the CI workflow that validates both fast auth tests and browser smoke coverage.

### Implemented Scope

The frontend now has a two-layer test strategy:

1. `Vitest + React Testing Library + MSW` for fast auth-focused unit and component coverage.
2. Docker-based browser smoke coverage for the real frontend build and authenticated dashboard flow.

The auth test suite covers:

* `AuthContext`
* `ProtectedRoute`
* `LoginPage`
* `RegisterPage`
* `VerifyEmailPage`
* `ForgotPasswordPage`
* `ResetPasswordPage`

### Implemented Files

Test infrastructure:

* `front/src/test/setup.ts`
* `front/src/test/renderWithProviders.tsx`
* `front/src/test/mocks/auth-handlers.ts`
* `front/src/test/fixtures/auth.ts`

Auth tests:

* `front/src/contexts/__tests__/AuthContext.test.tsx`
* `front/src/components/auth/__tests__/ProtectedRoute.test.tsx`
* `front/src/pages/login/__tests__/LoginPage.test.tsx`
* `front/src/pages/register/__tests__/RegisterPage.test.tsx`
* `front/src/pages/verify-email/__tests__/VerifyEmailPage.test.tsx`
* `front/src/pages/forgot-password/__tests__/ForgotPasswordPage.test.tsx`
* `front/src/pages/reset-password/__tests__/ResetPasswordPage.test.tsx`

Docker and CI:

* `front/Dockerfile.test`
* `docker-compose.yml` test services: `front-test`, `front-smoke`
* `.github/workflows/front-auth-tests.yml`

### Available NPM Scripts

The frontend package now exposes the following test commands:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:auth": "vitest run src/contexts/__tests__/AuthContext.test.tsx src/components/auth/__tests__/ProtectedRoute.test.tsx src/pages/login/__tests__/LoginPage.test.tsx src/pages/register/__tests__/RegisterPage.test.tsx src/pages/verify-email/__tests__/VerifyEmailPage.test.tsx src/pages/forgot-password/__tests__/ForgotPasswordPage.test.tsx src/pages/reset-password/__tests__/ResetPasswordPage.test.tsx",
    "test:coverage": "vitest run --coverage",
    "test:smoke": "node scripts/browser-smoke.cjs",
    "test:ci": "npm run test:auth && npm run build && npm run test:smoke"
  }
}
```

### Smoke Test Behavior

The smoke script is now Docker-friendly and no longer depends on Microsoft Edge.

Key changes:

* Playwright runs with standard Chromium.
* `SMOKE_BASE_URL` can be injected from Docker or CI.
* The smoke test bootstraps its own user through `POST /api/auth/register` before attempting the UI login flow.
* The script exits with a non-zero status if any smoke assertion fails.

This removes the dependency on a pre-seeded `dashboard@example.com` account and makes the login check reproducible in CI.

### Local Commands

Run auth tests locally with Node:

```powershell
Set-Location .\front
npm run test:auth
```

Run auth tests in Docker with the lightweight one-liner:

```powershell
docker run --rm -v "${PWD}:/app" -w /app node:22-alpine sh -lc "npm ci && npm run test:auth"
```

Run the Docker Compose test service from the repository root:

```powershell
$env:ENV_FILE = ".env.example"
docker compose -p frontend-auth-local --env-file .env.example --profile test run --rm --build front-test
```

Start the smoke stack and run the smoke container:

```powershell
$env:ENV_FILE = ".env.example"
docker compose -p frontend-auth-local --env-file .env.example up -d --build mongo redis minio minio-setup web front
docker compose -p frontend-auth-local --env-file .env.example --profile test run --rm --build front-smoke
docker compose -p frontend-auth-local --env-file .env.example down --volumes --remove-orphans
```

### Docker Design

`front/Dockerfile.test` is based on the official Playwright image so the same image can be reused for:

* `front-test` auth unit/component tests
* `front-smoke` browser smoke execution

The production frontend image remains unchanged in `front/Dockerfile`.

### CI Workflow

The repository now includes `.github/workflows/front-auth-tests.yml`.

The workflow performs these steps:

1. Run `front-test` in Docker.
2. Start `mongo`, `redis`, `minio`, `minio-setup`, `web`, and `front`.
3. Wait until the API and frontend are reachable.
4. Run `front-smoke` in Docker.
5. Print Docker Compose logs on failure.
6. Tear down the stack.

The workflow generates its own `.env.ci` file at runtime, so CI does not depend on a committed local `.env`.
It also uses a dedicated Compose project name so the smoke stack does not conflict with other running local services.

This keeps auth logic verification fast while still validating the real browser path to the protected dashboard.

### Current Validation Status

The implemented auth suite currently passes:

* `25` frontend auth tests
* Docker execution of `npm run test:auth`

Known note:

* `npm run lint` still reports pre-existing repository issues outside the scope of this testing change. The added test files do not introduce new linter diagnostics in the modified areas.

### Recommended Team Entry Points

For day-to-day auth regression checks, use:

```powershell
docker run --rm -v "${PWD}:/app" -w /app node:22-alpine sh -lc "npm ci && npm run test:auth"
```

For Compose-based validation that matches CI more closely, use:

```powershell
$env:ENV_FILE = ".env.example"
docker compose -p frontend-auth-local --env-file .env.example --profile test run --rm --build front-test
```

For full smoke validation, use:

```powershell
$env:ENV_FILE = ".env.example"
docker compose -p frontend-auth-local --env-file .env.example up -d --build mongo redis minio minio-setup web front
docker compose -p frontend-auth-local --env-file .env.example --profile test run --rm --build front-smoke
docker compose -p frontend-auth-local --env-file .env.example down --volumes --remove-orphans
```
