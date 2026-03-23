====
Бот ответов CourseVibe

Overview
This repository contains a Telegram bot and a small web admin interface for managing user submissions and message broadcasts. MongoDB is used as the primary data store, and Redis is used for queues and ephemeral state. Both services are started via Docker Compose.

Components

* Bot (aiogram 3.x, polling): Handles Telegram interactions, queues and notifications using aiogram 3.x in polling mode.
* Web (FastAPI): Provides an admin interface with authentication and basic pages.
* MongoDB: Primary data store.
* Redis: Queues and ephemeral state.

Requirements

* Docker и Docker Compose
* Python 3.11+ (только для локальной разработки вне Docker)

Environment Configuration
Переменные окружения загружаются из dotenv-файла. Укажите либо .env (похоже на прод), либо .env.dev (локально/для разработки). Файл compose использует ENV_FILE, если он задан, иначе по умолчанию берет .env.

Важно: не коммитьте секреты. Держите .env и .env.dev в секрете.

Скопируйте пример и подстройте значения:

1. Создайте .env на основе текущих открытых файлов в корне репозитория.

   * .env предназначен для серверных/прод-подобных значений
   * .env.dev — для локальной разработки

2. Обзор обязательных ключей (имена менять нельзя):

* BOT_NAME
* TELEGRAM_BOT_TOKEN
* TARGET_CHAT_ID (опционально)
* WEB_PORT
* WEB_APP_HOST
* WEB_SECRET_KEY
* MODERATOR_USERNAME
* MODERATOR_PASSWORD
* MONGO_DB_NAME
* REDIS_DB
* REDIS_QUEUE_NAME
* AUTO_MODERATION_QUEUE_NAME
* GOOGLE_GEMINI_API_KEY (опционально; LLM удален, оставлено для совместимости)
* AUTO_MODERATION_DAILY_LIMIT
* AUTO_MODERATION_PROMPT
* WEB_BASE_URL
* MASTER_USER_IDS
* BROADCAST_QUEUE_NAME

Running with Docker

1. Choose env file

   * For dev: set the env file when starting compose:

     * Windows PowerShell:
       `$env:ENV_FILE=".env.dev"; docker compose up -d --build`
   * For prod-like: omit `ENV_FILE` or set it to `.env`.

2. Start services
   `docker compose up -d --build`

3. Access web interface
   [http://localhost:WEB_PORT](http://localhost:WEB_PORT)

Local Development Without Docker (optional)

1. Create a virtual environment and install dependencies:
   `python -m venv .venv`
   `.\.venv\Scripts\Activate.ps1`
   `pip install -r requirements.txt`

2. Export environment (PowerShell):

   * Use values from `.env.dev` to set environment variables before starting processes.

3. Start MongoDB and Redis locally or via separate Docker containers.

4. Run the bot (prod-like, no hot reload):
   `python -m bot.main`

5. Run the web app:
   `uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload`

Notes

* Docker Compose reads variables directly from the env file, and services discover each other by names (`mongo`, `redis`).
* The legacy LLM module is removed. `GOOGLE_GEMINI_API_KEY` remains optional for compatibility.

## Hot reload (development)

### Local development with hot reload (watchfiles, PowerShell)

Prerequisites:

* Python 3.11+
* `.env` or `.env.dev` in the repository root (no secrets committed)

Install tools once:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Run the bot with hot reload (using `.env`):

```powershell
python -m dotenv -f .env run -- `
  python -m watchfiles `
    --filter python `
    --verbosity info `
    "python -m bot.main" `
    .\bot `
    .\shared
```

Key points:

* **Prod command**: `python -m bot.main` (single entrypoint).
* **Dev command**: wraps the prod command with `watchfiles` and `python-dotenv`.
* Watched directories: `./bot`, `./shared`.
* File extensions that trigger reload: `*.py` (Python sources).
* Ignored paths (via patterns or by avoiding writes there): `__pycache__/`, `.git/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `*.log`, `logs/`.

### Docker dev configuration with hot reload

For development, `docker-compose.override.yml` overrides only the bot command to enable hot reload inside the container while keeping volumes for `/app/bot` and `/app/shared`:

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

Run dev container (PowerShell):

```powershell
docker compose build bot
docker compose up bot
```

### Polling fallback for Docker/WSL

On some Windows/WSL setups, filesystem events inside containers may be unreliable. In such cases you can enable polling mode for `watchfiles` by adding the `--force-polling` flag to the watcher command (both locally and in Docker override).

Example (Docker override snippet):

```yaml
services:
  bot:
    command: >
      python -m watchfiles
      --filter python
      --verbosity info
      --force-polling
      "python -m bot.main"
      /app/bot
      /app/shared
```

### Known limitations with hot reload

* In-memory state (e.g., FSM state, caches, background tasks) does **not** survive process restarts in development.
* Frequent writes to files under `bot/` or `shared/` (for example, logs) can cause restart storms; keep logs outside these directories.
* On some Docker/WSL environments, you may need `--force-polling` for reliable restarts.

## Crypto exchange demo menu

The bot also exposes a demo crypto exchange menu implemented with Aiogram 3 FSM and Jinja2 templates (no real payments or DB):

- Main commands:
  - `/menu` — open the crypto exchange main menu.
  - `/exchange` — start the step-by-step exchange scenario.
  - `/rates` — view test rates for popular pairs.
  - `/orders` — stub screen for user orders.
  - `/profile` — static profile screen with limits.
  - `/support` — static support screen (`@your_support` placeholder).
  - `/cancel` — cancel the current FSM scenario and return to the main menu.

The menu is registered in the main bot entrypoint (`python -m bot.main`), so it works both in normal and hot-reload dev mode.
