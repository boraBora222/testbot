# Task: Docker Dev Override for Bot (Hot Reload)

- Objective: Run the bot in a container with hot reload using a dev override.
- Owner: DevOps/Dev
- Dependencies: Docker, Docker Compose; volumes for `./bot` and `./shared` already configured in `docker-compose.yml`.
- Success Criteria:
  - Container restarts the bot process when Python sources under `/app/bot` or `/app/shared` change.
  - No restart loops due to logs or cache writes.

## Steps

1) Create `docker-compose.override.yml` in the project root.

- Preferred: watchfiles
```yaml
services:
  bot:
    command: >
      python -m watchfiles
      --filter python
      --recursive
      --print
      --run "python -m bot.main"
      /app/bot /app/shared
```

- Alternative: watchdog
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

2) Rebuild & up
```powershell
docker compose build bot
docker compose up bot
```

## Notes
- Keep dev-only tools out of production images; prefer a `requirements-dev.txt` to install watch tools only in dev.
- On Windows/WSL2, watchfiles inside the container often reacts more reliably than watchdog.

## Validation
- Edit `bot/handlers/common.py`; observe restart logs and verify the new reply via the bot.
