### Hot reload implementation – task breakdown (dev‑only)

This document breaks the hot reload specification into concrete tasks for implementation in this repository.

---

### 1. Project audit and preconditions

- **Task 1.1 – Confirm aiogram version**
  - Check `requirements.txt` / `pyproject.toml` and imports to confirm the actual aiogram version (2.x vs 3.x).
  - Update `README.md` to explicitly state the aiogram version used by the project.

- **Task 1.2 – Determine run mode (polling vs webhook)**
  - Inspect the current bot startup code and decide whether the bot uses polling or webhook.
  - Document the chosen mode in `README.md`.

- **Task 1.3 – Normalize single entrypoint**
  - Identify how the bot is currently started (local scripts, Docker `command` / `ENTRYPOINT`).
  - Refactor, if necessary, to a single explicit entrypoint module, e.g. `bot.main`.
  - Ensure the bot can be started with a single command: `python -m bot.main`.
  - Update `README.md` to reference this entrypoint.

---

### 2. Bot startup and shutdown

- **Task 2.1 – Consolidate bot startup in `bot/main.py` (or equivalent)**
  - Ensure `bot/main.py` (or the chosen entrypoint module) contains:
    - logger configuration;
    - creation of `Bot`, `Dispatcher` / `Router`;
    - handler registration;
    - startup of polling/webhook.
  - Minimize side effects at import time, keeping initialization in a clear startup function or block.

- **Task 2.2 – Implement graceful shutdown (aiogram 3)**
  - For aiogram 3.x, add explicit HTTP session close on shutdown:
    - implement `on_shutdown(bot: Bot)` that calls `await bot.session.close()` alongside existing shutdown logic.
  - Verify that shutdown is invoked during normal process termination.

---

### 3. Watcher implementation

- **Task 3.1 – Choose and add watcher dependency**
  - Add `watchfiles` as the preferred watcher to dev dependencies (e.g. `requirements-dev.txt` or equivalent).
  - Optionally document `watchdog` (`watchdog.watchmedo`) as an alternative if needed.

- **Task 3.2 – Implement dev watcher script/module**
  - Create a dedicated watcher entrypoint (e.g. `dev_watcher.py` or `bot/dev_watcher.py`).
  - Responsibilities:
    - start the bot as a child process using the production command (e.g. `python -m bot.main`);
    - watch configured directories for changes;
    - on changes:
      - log which files changed;
      - gracefully terminate the current bot process;
      - wait for exit with a bounded timeout;
      - kill the process if it does not exit;
      - start a new bot process;
      - log success or failure of restart.

- **Task 3.3 – Configure paths to watch and ignore**
  - Watch paths (minimum):
    - `bot/`
    - `shared/` (if used)
    - any additional directories that contain bot code (handlers, middlewares, services, config).
  - Ignore paths:
    - `__pycache__/`, `.git/`, `.venv/` / `venv/`, `.pytest_cache/`, `.mypy_cache/`, `node_modules/` (if present);
    - log directories and files (`logs/`, `*.log`);
    - temporary files (`*.swp`, `*.tmp`, `*~`).
  - Encode these rules in the watcher configuration and reflect them in documentation.

- **Task 3.4 – Implement debounce and restart storm protection**
  - Add debounce logic so that a burst of file events from a single save triggers at most one restart.
  - Ensure that frequent saves (e.g. auto‑formatting) do not create restart storms.
  - Verify that only one bot process is active at a time.

- **Task 3.5 – Handle bot startup errors in the watcher**
  - Ensure that if the bot process fails to start (e.g. syntax error), the watcher:
    - logs the error output;
    - does not exit;
    - waits for further file changes;
    - retries starting the bot on the next change.

---

### 4. Dev vs prod commands

- **Task 4.1 – Define dev and prod commands for local runs**
  - Prod (local): document a command that starts only the bot, e.g. `python -m bot.main`.
  - Dev (local): document a command that starts the watcher (using `watchfiles` with `python-dotenv`), for example:
    - `python -m dotenv -f .env run -- python -m watchfiles ... "python -m bot.main" ./bot ./shared`
  - Ensure dev/prod commands are clearly separated in `README.md`.

- **Task 4.2 – Wire dev/prod in Docker and docker‑compose**
  - Prod:
    - ensure `Dockerfile` and `docker-compose.yml` start only the bot process (no watcher, no bind mount for hot reload).
  - Dev:
    - add or update `docker-compose.override.yml` to override only the bot service command to use the watcher (with `watchfiles`);
    - keep existing volumes for `/app/bot` and `/app/shared` so changes on the host are visible inside the container.

- **Task 4.3 – Add polling fallback for Docker/WSL**
  - Introduce a configuration option (e.g. env variable) to enable polling mode in the watcher if filesystem events are unreliable.
  - Document how to enable this mode for problematic environments.

---

### 5. Bot internals with hot reload

- **Task 5.1 – Review in‑memory state usage**
  - Identify any in‑memory state that is assumed to survive process lifetime (FSM, caches, etc.).
  - Decide which state is acceptable to lose on dev restarts and which must be externalized.
  - Document known limitations in `README.md` (e.g. FSM state reset on each restart).

- **Task 5.2 – Ensure correct handler registration**
  - Review handler registration to make sure:
    - it happens once per process start;
    - it is not triggered multiple times via repeated imports;
    - no dynamic re‑registration accumulates over time.
  - Add logging (if needed) to verify that handlers are registered once per startup.

- **Task 5.3 – Verify background tasks behavior**
  - Review any schedulers / background tasks:
    - ensure they start with the process and stop when the process exits;
    - verify that no orphan tasks remain after restarts.

---

### 6. Testing and verification

- **Task 6.1 – Implement and run basic hot reload test**
  - Start dev mode (local or Docker) with the watcher.
  - Change a visible reply in a handler and save.
  - Verify in logs that the watcher detected changes and restarted the bot process.
  - Confirm via the bot (e.g. Telegram/message) that the new reply is used.

- **Task 6.2 – Test behavior on code errors**
  - Introduce a syntax error in a handler file; save.
  - Verify that:
    - the watcher remains alive;
    - the startup error is logged.
  - Fix the error; save again.
  - Confirm that the bot restarts and responds normally.

- **Task 6.3 – Test duplicate handler / duplicate answer protection**
  - With dev mode running, perform several small edits and saves in the same handler.
  - After multiple restarts, send a single update to the bot.
  - Verify that:
    - the bot answers exactly once;
    - handler registration logs do not grow unbounded across restarts.

- **Task 6.4 – Test ignore rules**
  - Modify files that must be ignored (logs, files outside watched directories, temporary files) and save.
  - Verify that no restart is triggered and the bot PID stays the same.

- **Task 6.5 – Test debounce with frequent saves**
  - Trigger multiple quick saves on a watched file (e.g. via auto‑formatting).
  - Check watcher logs to ensure that restarts are debounced and there is at most one restart per burst.

- **Task 6.6 – Test Docker dev configuration**
  - Start the dev Docker configuration.
  - Change code on the host in a bind‑mounted directory.
  - Verify that the watcher inside the container restarts the bot and behavior updates.
  - If needed, enable polling mode and validate behavior again.

---

### 7. Documentation updates

- **Task 7.1 – Update README for dev/prod usage**
  - Document:
    - how to run the bot in dev mode (local and Docker);
    - how to run the bot in prod mode;
    - which directories and file extensions trigger reload;
    - how to enable polling fallback in Docker/WSL.

- **Task 7.2 – Document known limitations**
  - Add a “Known limitations” section covering:
    - in‑memory state reset on restarts;
    - any edge cases observed in WSL/Docker;
    - any non‑watched paths/configs that require manual restart.

