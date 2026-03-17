# Task: Aiogram Graceful Shutdown

- Objective: Ensure the bot closes network resources cleanly on restart to avoid leaks and warnings.
- Owner: Dev
- Dependencies: aiogram v3, current `bot/main.py`
- Success Criteria:
  - On restart/stop, HTTP session is closed without warnings.
  - DB and Redis shutdown remain intact.

## Steps

1) Add explicit session close in shutdown hook
```python
from aiogram import Bot

async def on_shutdown(bot: Bot):
    # existing: await db.disconnect_db(), await close_redis_pool(), etc.
    await bot.session.close()
```

2) Register hooks (already present)
- Verify that `dp.shutdown.register(on_shutdown)` remains in place.

3) Manual check
- Start with a watcher, perform a few rapid edits to trigger multiple restarts; ensure no lingering aiohttp warnings in logs.

## Validation
- Observe clean shutdown logs and absence of unclosed session warnings during frequent restarts.
