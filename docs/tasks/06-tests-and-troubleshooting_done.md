# Task: Test Plan and Troubleshooting for Hot Reload

- Objective: Validate hot reload end-to-end and document common pitfalls.
- Owner: QA/Dev
- Dependencies: Watcher running (local or Docker)
- Success Criteria:
  - All scenarios below confirmed working.

## Test Plan

1) Basic code change (handler)
- Edit a user-facing reply in `bot/handlers/common.py`; save.
- Expect one restart and new reply in Telegram.

2) Shared module update
- Edit code imported from `shared/` and save.
- Expect one restart and behavior change.

3) Exception and recovery
- Temporarily raise an exception inside a handler; save and observe error.
- Fix the code; save and expect clean restart and recovery.

4) Environment change (local)
- Run via `python -m dotenv -f .env run -- ...`.
- Change a value in `.env`, save; confirm the new value is visible after restart.

5) Rapid edits (debounce expectation)
- Make 2–3 quick saves; ensure watcher does not loop or flood restarts.

## Troubleshooting

- Restart storms
  - Exclude: `.git`, `.venv`, `__pycache__`, `*.log`.
  - Do not write logs inside `bot/` or `shared/`.

- No restart on changes in Docker
  - Ensure override command is applied and volumes for `/app/bot` and `/app/shared` are mounted.
  - Rebuild container: `docker compose build bot`.

- CLI not found
  - Use module form: `python -m watchfiles` or `python -m watchdog.watchmedo`.

- Env not applied (local)
  - Prefer: `python -m dotenv -f .env run -- <your command>`.
