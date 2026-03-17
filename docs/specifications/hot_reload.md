
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