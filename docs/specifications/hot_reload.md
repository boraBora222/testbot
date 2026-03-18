### Hot reload for the bot – specification (dev‑only)

This document describes how hot reload must work for this repository, how to run it in development (locally and in Docker), and how to test that it behaves correctly.

---

### 0. Goal

- Implement **dev‑only hot reload** for the aiogram bot via **full process restart**, without `importlib.reload` or any in‑process module reloading.
- In development, when source files change, the bot process is automatically restarted.
- In production, no watcher is started and no hot reload is used.

---

### 1. Constraints and principles

- **No in‑process reload**: do not use `importlib.reload` or similar tricks.
- **Only process restart**: hot reload is implemented by restarting a separate bot process.
- **Dev‑only**: watcher and hot reload are enabled only in development mode.
- **Production safe**: in production, bot is started directly (no watcher, no auto‑restart on file changes).
- **Watcher robustness**: if the bot code has an error and fails to start, the watcher must stay alive, log the error, and wait for the next change.

---

### 2. Preconditions and project facts

Before enabling hot reload, developers must fix and document:

- **aiogram version**:
  - Confirm actual version from `requirements.txt` / `pyproject.toml` and the imports in code (2.x vs 3.x).
  - Document it in `README.md`.

- **Run mode**:
  - Determine whether the bot is started via **polling** or **webhook** based on current code.
  - Document the decision in `README.md`.

- **Single entrypoint**:
  - There must be one explicit entrypoint module, e.g. `bot.main`.
  - The bot must be startable by a single command, e.g. `python -m bot.main`.
  - If the current project has multiple ad‑hoc ways to start the bot, they must be normalized to a single entrypoint first.

---

### 3. Target architecture (dev vs prod)

There must be two clear run modes.

#### 3.1. Production mode

- Only the bot process is started, **no watcher**.
- Typical command:

```powershell
python -m bot.main
```

- In `Dockerfile` and `docker-compose.yml` for production, the command must start the bot directly (no `watchfiles`, no `watchdog`).

#### 3.2. Development mode

- A dedicated **watcher process** is started instead of the bot:
  - It monitors project files and directories.
  - It starts the bot as a child process using the same command as in prod (e.g. `python -m bot.main`).
  - On change:
    - it gracefully stops the old bot process;
    - waits for termination with a bounded timeout;
    - kills the process if it does not exit in time;
    - starts a new bot process.

---

### 4. Watcher design

#### 4.1. Entrypoint for the bot

- The bot startup logic must be consolidated into a single module, for example `bot/main.py`, with:
  - logger configuration;
  - creation of `Bot`, `Dispatcher` / `Router`;
  - handler registration;
  - polling/webhook startup.
- Side effects at import time must be minimized: handler registration and initialization should happen during startup, not purely on imports.

#### 4.2. Watcher implementation

- Use a **ready‑made file watcher**, do not write a naive mtime polling loop unless there is a proven limitation.
- Preferred library: **`watchfiles`** (works well on Windows/WSL2/Docker).
- Alternative (if needed): **`watchdog.watchmedo`** with strict patterns and ignore rules.

The watcher must:

- start the bot as a child process (e.g. `python -m bot.main`);
- monitor selected project paths for changes;
- on change:
  - log the event and list of changed files;
  - attempt graceful shutdown of the current bot process;
  - wait with a bounded timeout;
  - if the process does not exit, kill it;
  - start a new bot process;
  - log success/failure of restart.

#### 4.3. Debounce and protection from restart storms

- The watcher must implement:
  - **debounce** of changes (minimum interval between restarts);
  - grouping multiple file events from a single save into one restart;
  - ignoring temporary editor files.
- Implement debounce either via `watchfiles` built‑in options or in the watcher loop itself.

#### 4.4. Paths to watch

Only relevant directories must be watched. For this repository the minimum set is:

- `bot/`
- `shared/` (if used for shared logic)
- any additional app‑level directories that contain bot code (handlers, middlewares, services, config modules).

Configuration must explicitly define which directories are watched and this list must be documented.

#### 4.5. Paths to ignore

The watcher must ignore at least:

- `__pycache__/`
- `.git/`
- `.venv/` / `venv/`
- `.pytest_cache/`
- `.mypy_cache/`
- `node_modules/` (if present)
- log directories and files, e.g. `logs/`, `*.log`
- temporary editor files:
  - `*.swp`
  - `*.tmp`
  - `*~`

#### 4.6. File extensions that trigger restart

Minimum:

- `*.py`

Optional (only if actually used by this project and clearly documented):

- `.env`
- `*.yaml`, `*.yml`
- `*.toml`

The final extension list must be explicitly encoded in watcher configuration and described in `README.md`.

#### 4.7. Behavior on bot startup errors

If, after a code change, the bot fails to start (for example, due to a syntax error):

- the watcher **must not** exit;
- the startup error must be logged (stderr of the bot process);
- the watcher waits for further file changes;
- after the code is fixed and saved, the watcher must automatically attempt to start the bot again.

#### 4.8. Process termination policy

On restart:

1. Send **graceful termination** signal to the child (on Windows use `.terminate()`, on POSIX SIGINT/SIGTERM).
2. Wait for process exit with a bounded timeout.
3. If the process is still alive after timeout, kill it (`.kill()` / SIGKILL).
4. Only then start a new bot process.

The watcher must never wait indefinitely for old processes to exit.

#### 4.9. Logging requirements

The watcher must log:

- watcher startup;
- list of watched directories and glob patterns;
- detection of file changes;
- which files triggered the restart;
- attempt to stop the old process (PID, timeout settings);
- success or failure of graceful shutdown and whether a kill was required;
- startup of a new process (PID, command);
- any error during bot startup (with stderr content where possible).

From logs, it must be clear:

- **why** a restart was triggered;
- **which** process is currently active;
- **what** happened during unsuccessful startups.

---

### 5. Developer docs – how to run hot reload

#### 5.1. Prerequisites

- Environment variables must be set from `.env`:
  - Locally: either export them in PowerShell (`$env:KEY='value'`) or use `python -m dotenv -f .env run -- ...` (preferred).
  - In Docker Compose, they are injected via `env_file`.

#### 5.2. Local development (PowerShell) – using `watchfiles` (preferred)

Install tools once:

```powershell
python -m pip install --upgrade pip
python -m pip install watchfiles python-dotenv
```

Start the bot with hot reload:

```powershell
python -m dotenv -f .env run -- `
  python -m watchfiles `
    --filter python `
    --verbosity info `
    "python -m bot.main" `
    .\bot `
    .\shared
```

Notes:

- `--filter python` focuses on Python sources.
- Recursive watching is the default; use `--non-recursive` if needed.
- `--verbosity info` prints restarts and changed paths.
- Adjust watched directories (`.\bot`, `.\shared`) to match real project layout if it changes.

#### 5.3. Local development – alternative `watchdog.watchmedo` (if needed)

```powershell
python -m pip install watchdog python-dotenv
python -m dotenv -f .env run -- `
  python -m watchdog.watchmedo auto-restart `
    --recursive `
    --patterns="*.py;*.pyi" `
    --ignore-patterns="*.pyc;*~;__pycache__/*;.git/*;.venv/*;.log" `
    -d .\bot `
    -d .\shared `
    -- python -m bot.main
```

This must still respect the rules above (debounce, ignore rules, bounded shutdown).

---

### 6. Docker / docker‑compose

#### 6.1. Dev configuration

- In `docker-compose.override.yml`, override only the **bot command**, keeping existing volumes for `/app/bot` and `/app/shared` (as configured in `docker-compose.yml`).
- Example dev override with `watchfiles` (preferred):

```yaml
services:
  bot:
    command: >
      python -m watchfiles
      --filter python
      --verbosity info
      "python -m bot.main"
      /app/bot
      /app/shared
```

- Example dev override with `watchdog`:

```yaml
services:
  bot:
    command: >
      python -m watchdog.watchmedo auto-restart
      --recursive
      --patterns="*.py;*.pyi"
      --ignore-patterns="*.pyc;*~;__pycache__/*;.git/*;.venv/*;.log"
      -d /app/bot -d /app/shared --
      python -m bot.main
```

Run dev container:

```powershell
docker compose build bot
docker compose up bot
```

Recommendations:

- Keep dev tools (`watchfiles`, `watchdog`) in `requirements-dev.txt` or an equivalent dev dependencies file; keep the prod image minimal.
- On Windows/WSL2, `watchfiles` inside the container usually reacts more reliably to bind‑mount changes.

#### 6.2. Prod configuration

- In prod compose and images:
  - do **not** mount source code purely for hot reload;
  - do **not** start watcher processes;
  - start only the bot (e.g. `python -m bot.main`).

#### 6.3. Fallback for Docker/WSL

- If filesystem events inside containers are unstable (e.g. certain Windows/WSL setups):
  - provide a **polling mode** for the watcher, enabled via configuration (env var or flag);
  - do not rely on manual code patches to change watcher behavior.

---

### 7. Bot code requirements

#### 7.1. State

- In‑memory state must not be assumed to survive a reload.
- It is acceptable to lose, on dev restarts:
  - temporary caches;
  - local objects;
  - in‑memory FSM state, if the team accepts this trade‑off.
- If some state is critical and cannot be lost, it must be stored in an external backend (DB, cache, etc.).

#### 7.2. Handler registration

- Handlers must be registered **once per process start**.
- Code must be checked to ensure:
  - there is no handler registration purely on module import that could run multiple times;
  - there is no dynamic re‑registration that would accumulate upon restarts.
- For a single incoming update, the bot should produce **one** reply even after many dev restarts.

#### 7.3. Background tasks

- Any scheduler or background tasks must:
  - start again on each process start;
  - not leave orphan tasks when the process is stopped (normally this is satisfied when the process exits cleanly).

#### 7.4. Graceful shutdown (aiogram 3)

To avoid dangling HTTP connections during frequent restarts, explicitly close the `Bot` HTTP session on shutdown:

```python
from aiogram import Bot

async def on_shutdown(bot: Bot):
    # existing shutdown logic: close DB/Redis, etc.
    await bot.session.close()
```

---

### 8. Test plan (what to verify)

#### 8.1. Basic scenario

1. Start dev mode (local or Docker) with the watcher.
2. Verify that the bot responds normally.
3. Change a visible reply in a handler (for example, in `bot/handlers/common.py`), save.
4. Check watcher logs:
   - it detected changes;
   - it restarted the bot process.
5. Send a request/message to the bot and verify that the reply uses the **new** text.

#### 8.2. Code error

1. Introduce a clear syntax error in a handler file.
2. Save the file.
3. Verify that:
   - the watcher stays alive;
   - the bot startup error is visible in logs.
4. Fix the error and save again.
5. Verify that the watcher automatically restarts the bot and the bot responds again.

#### 8.3. Protection from duplicate handlers / answers

1. Start dev mode.
2. Perform several small code edits in the same handler, saving after each change.
3. After a few restarts, send a single message/update to the bot.
4. Verify that:
   - the bot answers **exactly once**;
   - logs show handler registration once per process start, without growth over time.

#### 8.4. Ignore rules

1. Modify a file that must be ignored (e.g. a log file or a file outside watched directories).
2. Save it.
3. Verify that:
   - the watcher does not trigger a restart;
   - the bot process stays the same.

#### 8.5. Frequent saves / debounce

1. Trigger multiple quick saves (e.g. via auto‑formatting a Python file).
2. Observe watcher logs.
3. Verify that:
   - a restart storm does not occur;
   - restarts are debounced (there may be a single restart per burst of changes);
   - only one bot process is active at any time.

#### 8.6. Docker

1. Start the dev configuration in Docker.
2. Change code on the host in a bind‑mounted directory.
3. Verify that, inside the container:
   - the watcher detects the change and restarts the bot process;
   - the bot serves updated behavior.
4. If file events do not work reliably:
   - enable polling mode;
   - confirm that restarts still happen when files change.

---

### 9. Acceptance criteria

The hot reload implementation is considered complete when:

- In dev mode, the bot automatically restarts when relevant source files change.
- In prod mode, there is no watcher and no hot reload.
- On code errors, the watcher does not crash and continues watching.
- There are no duplicate handlers and no duplicate responses after multiple restarts.
- Debounce and ignore rules are in place and working.
- There is a working Docker dev configuration with hot reload.
- `README.md` documents:
  - how to run dev and prod;
  - which files/directories trigger reload;
  - known limitations (e.g. in‑memory state loss, WSL specifics).

Short task formulation: **implement dev‑only hot reload for the aiogram bot via separate process restart (no `importlib.reload`), using a ready‑made watcher with debounce, ignore rules, proper process shutdown, Docker/WSL polling fallback, and clear separation of dev/prod commands. The watcher must survive bot code errors and continue operating.**


### План (кратко, RU)
- Предпочтительно: использовать `watchfiles` (легче и стабильнее на Windows/WSL2/Docker). Альтернатива — `watchdog.watchmedo` с жёсткими паттернами/игнорами.
- Локально запускать watcher по `./bot` и `./shared`, загружая `.env` через `python-dotenv`.
- В Docker (dev) переопределять `command` через `docker-compose.override.yml`; тома `./bot` и `./shared` уже смонтированы.
- Добавить graceful shutdown в aiogram: закрывать HTTP‑сессию бота в `on_shutdown`.
- Тесты: изменить хэндлер, изменить импорт из `shared`, сымитировать исключение, проверить обновление `.env`.

### Developer Docs (EN)

- Prereqs
  - Ensure environment variables are set (use your `.env` values). Locally either export them in PowerShell via `$env:KEY='value'` or use `python -m dotenv run -- ...`. In Docker Compose they are already injected via `env_file`.

- Local development (PowerShell)
  1) Preferred: watchfiles
     ```powershell
     python -m pip install --upgrade pip
     python -m pip install watchfiles python-dotenv
     python -m dotenv -f .env run -- python -m watchfiles --filter python --verbosity info "python -m bot.main" .\bot .\shared
     ```
     Notes:
     - `--filter python` focuses on Python sources.
     - Recursive watching is the default; use `--non-recursive` to disable.
     - `--verbosity info` prints restarts and changed paths (or use `--verbose`).

  2) Alternative: watchdog (watchmedo)
     ```powershell
     python -m pip install watchdog python-dotenv
     python -m dotenv -f .env run -- python -m watchdog.watchmedo auto-restart `
       --recursive `
       --patterns="*.py;*.pyi" `
       --ignore-patterns="*.pyc;*~;__pycache__/*;.git/*;.venv/*;*.log" `
       -d .\bot -d .\shared -- python -m bot.main
     ```

- Docker Compose (dev)
  - Create `docker-compose.override.yml` and override only the bot command. Keep volumes for `/app/bot` and `/app/shared` (already present in `docker-compose.yml`).

  Example override with watchfiles (preferred):
  ```yaml
  services:
    bot:
      command: >
        python -m watchfiles
        --filter python
        --verbosity info
        "python -m bot.main"
        /app/bot /app/shared
  ```

  Example override with watchdog:
  ```yaml
  services:
    bot:
      command: >
        python -m watchdog.watchmedo auto-restart
        --recursive
        --patterns="*.py;*.pyi"
        --ignore-patterns="*.pyc;*~;__pycache__/*;.git/*;.venv/*;*.log"
        -d /app/bot -d /app/shared --
        python -m bot.main
  ```

  Then:
  ```powershell
  docker compose build bot
  docker compose up bot
  ```

  Recommendations:
  - Keep dev tools (watchfiles/watchdog) in `requirements-dev.txt`; keep prod image clean.
  - On Windows/WSL2, watchfiles inside the container usually reacts more reliably to bind-mount changes.

-- Graceful shutdown (aiogram 3)

Add explicit HTTP session close on shutdown to avoid dangling connections during frequent restarts:

```python
from aiogram import Bot

async def on_shutdown(bot: Bot):
    # existing shutdown logic: close DB/Redis, etc.
    await bot.session.close()
```

- Test the hot reload
  1) Start the watcher (locally or via Docker).
  2) Edit a visible response in `bot/handlers/common.py` (e.g., change a reply message), save; verify auto-restart and new reply.
  3) Change an imported function in `shared/`; verify auto-restart and behavior update.
  4) Intentionally raise an exception in a handler; fix it; ensure restart and recovery.
  5) Change a value in `.env` (local via `python -m dotenv -f .env run -- ...`); ensure the restarted process sees the new env.

- Troubleshooting
  - Avoid writing logs inside `bot/` or `shared/`; otherwise log writes may trigger restart storms.
  - Exclude noisy paths: `.git`, `.venv`, `__pycache__`, `*.log` via filters/ignore patterns (see examples above).
  - If `watchmedo` is “not found”, use the module form (`python -m watchdog.watchmedo`).
  - If env vars aren’t loaded locally, prefer `python -m dotenv -f .env run -- ...` over implicit `.env` loading (the app reads from actual environment).

Коротко: для локалки и Docker выбирайте `watchfiles` (предпочтительно) или `watchdog` по примерам выше; изменения в `bot`/`shared` должны мгновенно перезапускать процесс.

This document provides exact PowerShell/Docker commands and an expanded test plan tailored to this repository.