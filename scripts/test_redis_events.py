import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as redis

from shared.config import settings


async def send_order_status_event() -> None:
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        event = {
            "type": "order_status_change",
            "order_id": "ORD-00001",
            "old_status": "new",
            "new_status": "processing",
            "reason": "Manager started processing the order.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await client.rpush(settings.order_status_queue_name, json.dumps(event))
        print(f"Queued event to {settings.order_status_queue_name}: {event}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(send_order_status_event())
