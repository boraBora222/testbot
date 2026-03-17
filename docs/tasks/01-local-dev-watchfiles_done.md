# Task: Local Dev Hot Reload with watchfiles

- Objective: Enable fast hot reload locally using watchfiles and python-dotenv.
- Owner: Dev
- Dependencies: Python, pip, `.env` present at repo root
- Success Criteria:
  - Saving any `.py` file under `./bot` or `./shared` triggers a single restart.
  - The terminal shows which file triggered the restart.
  - The bot replies reflect the latest code after restart.

## Steps (PowerShell)

1) Install tools
```powershell
python -m pip install --upgrade pip
python -m pip install watchfiles python-dotenv
```

2) Run with `.env` loaded
```powershell
python -m dotenv -f .env run -- python -m watchfiles --filter python --recursive --print --run "python -m bot.main" .\bot .\shared
```

Notes
- `--filter python` focuses on Python sources.
- `--recursive` watches subdirectories.
- `--print` shows the changed paths.
- Avoid writing logs inside `bot/` or `shared/` to prevent restart storms.

## Validation
- Edit `bot/handlers/common.py` to change a visible reply string; save, then message the bot and verify the updated reply.
- Edit code used from `shared/` and verify the new behavior after auto-restart.
