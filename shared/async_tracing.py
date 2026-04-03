from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

TRACE_FIELD = "_async_trace"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def add_async_trace(
    payload: dict[str, Any],
    *,
    producer: str,
    queue_name: str,
    event_name: str | None = None,
    trace_id: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    traced_payload = dict(payload)
    existing_trace = get_async_trace(payload)

    if not existing_trace.get("trace_id"):
        existing_trace["trace_id"] = trace_id or uuid4().hex[:12]
    if not existing_trace.get("published_at"):
        existing_trace["published_at"] = published_at or utc_now_iso()

    existing_trace["producer"] = producer
    existing_trace["queue_name"] = queue_name
    if event_name:
        existing_trace["event_name"] = event_name

    traced_payload[TRACE_FIELD] = existing_trace
    return traced_payload


def get_async_trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    trace_payload = payload.get(TRACE_FIELD)
    if isinstance(trace_payload, Mapping):
        return dict(trace_payload)
    return {}


def duration_ms(started_at: str | datetime | None, finished_at: str | datetime | None = None) -> float | None:
    start_dt = _coerce_datetime(started_at)
    finish_dt = _coerce_datetime(finished_at) or utc_now()
    if start_dt is None or finish_dt is None:
        return None
    return round((finish_dt - start_dt).total_seconds() * 1000, 2)


def format_async_trace(
    payload: Mapping[str, Any],
    *,
    stage: str,
    queue_name: str,
    finished_at: str | datetime | None = None,
    recipient_id: int | None = None,
) -> str:
    trace = get_async_trace(payload)
    parts: list[str] = [f"stage={stage}", f"queue={queue_name}"]

    trace_id = trace.get("trace_id")
    if trace_id:
        parts.append(f"trace_id={trace_id}")

    producer = trace.get("producer")
    if producer:
        parts.append(f"producer={producer}")

    event_name = trace.get("event_name") or payload.get("event") or payload.get("type")
    if event_name:
        parts.append(f"event={event_name}")

    latency = duration_ms(trace.get("published_at"), finished_at)
    if latency is not None:
        metric_name = "queue_latency_ms" if stage == "dequeued" else "total_latency_ms"
        parts.append(f"{metric_name}={latency:.2f}")

    if recipient_id is not None:
        parts.append(f"recipient_id={recipient_id}")

    return " ".join(parts)


def _coerce_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    candidate = value.strip()
    if candidate == "":
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
