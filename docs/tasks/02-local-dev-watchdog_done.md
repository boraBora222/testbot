# Task: Local Dev Hot Reload with watchdog (watchmedo)

- Objective: Provide an alternative watcher using watchdog's `watchmedo`.
- Owner: Dev
- Dependencies: Python, pip, `.env` present at repo root
- Success Criteria:
  - Saving `.py` files under `./bot` or `./shared` triggers exactly one restart.
  - No restarts from cache/log changes.

## Steps (PowerShell)

1) Install tools
```powershell
python -m pip install watchdog python-dotenv
```

2) Run with strict patterns and ignores
```powershell
python -m dotenv -f .env run -- python -m watchdog.watchmedo auto-restart `
  --recursive `
  --patterns="*.py;*.pyi" `
  --ignore-patterns="*.pyc;*~;__pycache__/*;.git/*;.venv/*;*.log" `
  -d .\bot -d .\shared -- python -m bot.main
```

Notes
- Keep ignores updated to avoid infinite restart loops.
- Prefer this only if `watchfiles` is not feasible on your machine.

## Validation
- Same as the watchfiles task: modify `bot/handlers/common.py`, verify restart and updated reply.
