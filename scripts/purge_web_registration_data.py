"""Purge website registration footprint from MongoDB (shadow exchange users, user_id < 0).

Website sessions and in-memory users live in the web process; restart the web container after
running this script so /auth state is cleared.

Usage (from project root, with compose env applied to the web container):

  docker compose exec web python /app/scripts/purge_web_registration_data.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from shared import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> int:
    await db.connect_db()
    try:
        stats = await db.purge_web_registration_footprint()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        logger.info(
            "Purge finished. Restart the web service so in-memory web users and auth sessions are cleared."
        )
    finally:
        await db.disconnect_db()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
