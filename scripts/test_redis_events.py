import argparse
import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as redis

from shared.async_tracing import add_async_trace, get_async_trace
from shared.config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send traced async notification probes to Redis queues.")
    parser.add_argument(
        "--kind",
        choices=("manager", "broadcast", "order-status"),
        default="manager",
        help="Which queue payload to send.",
    )
    parser.add_argument("--user-id", type=int, default=1, help="Telegram user id for broadcast payloads.")
    parser.add_argument("--order-id", default="ORD-00001", help="Order id for order-status payloads.")
    parser.add_argument("--text", default="Latency probe from scripts/test_redis_events.py", help="Message text for broadcast or manager payloads.")
    parser.add_argument(
        "--manager-event",
        choices=("support_message", "material_received", "new_order"),
        default="support_message",
        help="Manager notification event type.",
    )
    parser.add_argument("--trace-id", default=None, help="Optional trace id override.")
    return parser.parse_args()


def build_payload(args: argparse.Namespace) -> tuple[str, dict]:
    if args.kind == "broadcast":
        queue_name = settings.broadcast_queue_name
        payload = {
            "type": "broadcast",
            "user_id": args.user_id,
            "text": args.text,
        }
        return queue_name, add_async_trace(
            payload,
            producer="scripts.test_redis_events",
            queue_name=queue_name,
            event_name="broadcast",
            trace_id=args.trace_id,
        )

    if args.kind == "order-status":
        queue_name = settings.order_status_queue_name
        payload = {
            "type": "order_status_change",
            "order_id": args.order_id,
            "old_status": "new",
            "new_status": "processing",
            "reason": "Latency probe advanced the order.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return queue_name, add_async_trace(
            payload,
            producer="scripts.test_redis_events",
            queue_name=queue_name,
            event_name="order_status_change",
            trace_id=args.trace_id,
        )

    queue_name = settings.notify_managers_queue_name
    payload = {
        "type": "notify_managers",
        "event": args.manager_event,
        "user_id": args.user_id,
        "username": f"probe_{args.user_id}",
        "text": args.text,
    }
    if args.manager_event == "new_order":
        payload["order_id"] = args.order_id
        payload["summary"] = "Async notification probe order"
    else:
        payload["content_type"] = "text"

    return queue_name, add_async_trace(
        payload,
        producer="scripts.test_redis_events",
        queue_name=queue_name,
        event_name=args.manager_event,
        trace_id=args.trace_id,
    )


async def send_probe(args: argparse.Namespace) -> None:
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    queue_name, payload = build_payload(args)
    try:
        await client.rpush(queue_name, json.dumps(payload, default=str))
        trace = get_async_trace(payload)
        print(
            f"Queued probe to {queue_name}. "
            f"kind={args.kind} trace_id={trace.get('trace_id')} published_at={trace.get('published_at')}"
        )
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(send_probe(parse_args()))
