from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

TRACE_FIELD = "_async_trace"
ASYNC_ENVELOPE_VERSION = "v1"
ASYNC_ENVELOPE_META_FIELD = "meta"
ASYNC_ENVELOPE_PAYLOAD_FIELD = "payload"
CORRELATION_ID_HEADER = "x-correlation-id"
LEGACY_REQUEST_ID_HEADER = "x-request-id"
_correlation_id_context: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def normalize_correlation_id(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    return candidate or None


def generate_correlation_id() -> str:
    return uuid4().hex[:12]


def get_correlation_id() -> str | None:
    return normalize_correlation_id(_correlation_id_context.get())


def get_or_create_correlation_id(correlation_id: str | None = None) -> str:
    normalized = normalize_correlation_id(correlation_id) or get_correlation_id()
    return normalized or generate_correlation_id()


def bind_correlation_id(correlation_id: str | None = None) -> Token[str | None]:
    return _correlation_id_context.set(get_or_create_correlation_id(correlation_id))


def reset_correlation_id(token: Token[str | None]) -> None:
    _correlation_id_context.reset(token)


def extract_correlation_id(headers: Mapping[str, Any]) -> str | None:
    for header_name in (CORRELATION_ID_HEADER, LEGACY_REQUEST_ID_HEADER):
        value = headers.get(header_name)
        if isinstance(value, str):
            normalized = normalize_correlation_id(value)
            if normalized is not None:
                return normalized
    return None


def add_async_trace(
    payload: dict[str, Any],
    *,
    producer: str,
    queue_name: str,
    event_name: str | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    traced_payload = dict(payload)
    existing_trace = get_async_trace(payload)

    resolved_correlation_id = get_or_create_correlation_id(
        correlation_id
        or trace_id
        or existing_trace.get("correlation_id")
        or existing_trace.get("trace_id")
    )
    existing_trace["correlation_id"] = resolved_correlation_id
    existing_trace["trace_id"] = resolved_correlation_id
    if not existing_trace.get("published_at"):
        existing_trace["published_at"] = published_at or utc_now_iso()

    existing_trace["producer"] = producer
    existing_trace["queue_name"] = queue_name
    if event_name:
        existing_trace["event_name"] = event_name

    traced_payload[TRACE_FIELD] = existing_trace
    return traced_payload


def build_async_message(
    payload: dict[str, Any],
    *,
    producer: str,
    queue_name: str,
    event_name: str | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    traced_payload = add_async_trace(
        payload,
        producer=producer,
        queue_name=queue_name,
        event_name=event_name,
        correlation_id=correlation_id,
        trace_id=trace_id,
        published_at=published_at,
    )
    message = dict(traced_payload)
    message[ASYNC_ENVELOPE_META_FIELD] = get_async_trace(traced_payload)
    message[ASYNC_ENVELOPE_PAYLOAD_FIELD] = {
        key: value
        for key, value in traced_payload.items()
        if key not in {TRACE_FIELD, ASYNC_ENVELOPE_META_FIELD, ASYNC_ENVELOPE_PAYLOAD_FIELD, "version"}
    }
    message["version"] = ASYNC_ENVELOPE_VERSION
    return message


def is_async_envelope(payload: Mapping[str, Any]) -> bool:
    version = payload.get("version")
    return (
        isinstance(version, str)
        and normalize_correlation_id(version) is not None
        and isinstance(payload.get(ASYNC_ENVELOPE_META_FIELD), Mapping)
        and isinstance(payload.get(ASYNC_ENVELOPE_PAYLOAD_FIELD), Mapping)
    )


def get_async_version(payload: Mapping[str, Any]) -> str | None:
    version = payload.get("version")
    return normalize_correlation_id(version) if isinstance(version, str) else None


def get_async_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if is_async_envelope(payload):
        business_payload = dict(payload[ASYNC_ENVELOPE_PAYLOAD_FIELD])
        trace = get_async_trace(payload)
        if trace:
            business_payload.setdefault(TRACE_FIELD, trace)
        return business_payload

    business_payload = dict(payload)
    trace = get_async_trace(payload)
    if trace:
        business_payload[TRACE_FIELD] = trace
    return business_payload


def get_async_trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    if is_async_envelope(payload):
        normalized_trace = _normalize_async_trace_payload(payload.get(ASYNC_ENVELOPE_META_FIELD))
        if normalized_trace:
            return normalized_trace
        nested_payload = payload.get(ASYNC_ENVELOPE_PAYLOAD_FIELD)
        if isinstance(nested_payload, Mapping):
            normalized_trace = _normalize_async_trace_payload(nested_payload.get(TRACE_FIELD))
            if normalized_trace:
                return normalized_trace

    normalized_trace = _normalize_async_trace_payload(payload.get(TRACE_FIELD))
    if normalized_trace:
        return normalized_trace
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
    business_payload = get_async_payload(payload)
    parts: list[str] = [f"stage={stage}", f"queue={queue_name}"]

    version = get_async_version(payload)
    if version:
        parts.append(f"version={version}")

    correlation_id = trace.get("correlation_id")
    if correlation_id:
        parts.append(f"correlation_id={correlation_id}")

    producer = trace.get("producer")
    if producer:
        parts.append(f"producer={producer}")

    event_name = trace.get("event_name") or business_payload.get("event") or business_payload.get("type")
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


def _normalize_async_trace_payload(trace_payload: object) -> dict[str, Any]:
    if not isinstance(trace_payload, Mapping):
        return {}
    normalized_trace = dict(trace_payload)
    correlation_id = get_or_create_correlation_id(
        normalized_trace.get("correlation_id") or normalized_trace.get("trace_id")
    )
    normalized_trace["correlation_id"] = correlation_id
    normalized_trace.setdefault("trace_id", correlation_id)
    return normalized_trace
