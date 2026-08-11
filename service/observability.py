"""Low-dependency A6 telemetry: JSON events, traces, and Prometheus text."""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import RuntimeSettings


_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_ticket_id: contextvars.ContextVar[str] = contextvars.ContextVar("ticket_id", default="")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    trace_id: str
    span_id: str

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-01"


def new_request_context(request_id: str | None, traceparent: str | None) -> RequestContext:
    rid = (request_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", rid):
        rid = f"req-{secrets.token_hex(8)}"
    match = _TRACEPARENT.fullmatch((traceparent or "").strip().lower())
    trace_id = match.group(1) if match else secrets.token_hex(16)
    return RequestContext(request_id=rid, trace_id=trace_id, span_id=secrets.token_hex(8))


def bind_context(context: RequestContext, ticket_id: str = "") -> None:
    _request_id.set(context.request_id)
    _trace_id.set(context.trace_id)
    _ticket_id.set(ticket_id)


def bind_ticket(ticket_id: str) -> None:
    _ticket_id.set(ticket_id)


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


_SENSITIVE_KEYS = {
    "authorization", "api_key", "token", "secret", "password", "ticket_text",
    "raw_text", "email", "customer_text", "approved_payload", "draft_response",
}


def _sanitize(value: Any, *, key: str = "") -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in _SENSITIVE_KEYS):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:512]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:256]


class TraceStore:
    """Bounded single-process trace store; not durable or distributed."""

    def __init__(self, max_traces: int = 200, max_events_per_trace: int = 100):
        self._order: deque[str] = deque(maxlen=max_traces)
        self._events: dict[str, deque[dict[str, Any]]] = {}
        self._max_events = max_events_per_trace
        self._lock = threading.Lock()

    def append(self, trace_id: str, event: dict[str, Any]) -> None:
        if not trace_id:
            return
        with self._lock:
            if trace_id not in self._events:
                if len(self._order) == self._order.maxlen:
                    oldest = self._order.popleft()
                    self._events.pop(oldest, None)
                self._order.append(trace_id)
                self._events[trace_id] = deque(maxlen=self._max_events)
            self._events[trace_id].append(event)

    def get(self, trace_id: str) -> list[dict[str, Any]] | None:
        with self._lock:
            events = self._events.get(trace_id)
            return list(events) if events is not None else None


class MetricRegistry:
    """In-process staging SLIs with Prometheus-compatible exposition."""

    _LATENCY_BUCKETS = (5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0)

    def __init__(self):
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted((labels or {}).items()))

    def inc(self, name: str, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += amount

    def observe(self, name: str, value_ms: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._histograms[self._key(name, labels)].append(max(0.0, float(value_ms)))

    @staticmethod
    def _labels(labels: tuple[tuple[str, str], ...], extra: tuple[str, str] | None = None) -> str:
        values = list(labels)
        if extra:
            values.append(extra)
        if not values:
            return ""
        return "{" + ",".join(f'{k}="{v}"' for k, v in values) + "}"

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = dict(self._counters)
            histograms = {key: list(values) for key, values in self._histograms.items()}
        for (name, labels), value in sorted(counters.items()):
            lines.append(f"{name}{self._labels(labels)} {value:g}")
        for (name, labels), values in sorted(histograms.items()):
            for boundary in self._LATENCY_BUCKETS:
                count = sum(1 for value in values if value <= boundary)
                lines.append(f"{name}_bucket{self._labels(labels, ('le', str(boundary)))} {count}")
            lines.append(f"{name}_bucket{self._labels(labels, ('le', '+Inf'))} {len(values)}")
            lines.append(f"{name}_count{self._labels(labels)} {len(values)}")
            lines.append(f"{name}_sum{self._labels(labels)} {sum(values):g}")
        return "\n".join(lines) + "\n"


class Telemetry:
    _COMMON_FIELDS = (
        "route", "intent", "action", "grounding_level", "provider", "model",
        "provider_attempt", "fallback_used", "tool_calls", "latency_ms", "error_type",
        "review_state", "execution_state", "model_version", "prompt_version",
        "policy_version", "kb_version",
    )

    def __init__(self, settings: RuntimeSettings, *, logger: logging.Logger | None = None):
        self.settings = settings
        self.traces = TraceStore()
        self.metrics = MetricRegistry()
        self.logger = logger or logging.getLogger("support_copilot.ops")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

    def event(self, event: str, *, level: str = "INFO", ticket_id: str | None = None, **fields: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "timestamp": utc_now(),
            "level": level,
            "event": event,
            "request_id": _request_id.get(),
            "trace_id": _trace_id.get(),
            "ticket_id": ticket_id if ticket_id is not None else _ticket_id.get(),
            "deployment_version": self.settings.deployment_version,
            "git_sha": self.settings.git_sha,
            "deployment_mode": self.settings.deployment_mode.value,
            "prompt_version": self.settings.prompt_version,
            "policy_version": self.settings.policy_version,
        }
        for name in self._COMMON_FIELDS:
            record.setdefault(name, None)
        record.update(_sanitize(fields))
        sanitized = _sanitize(record)
        self.traces.append(str(sanitized.get("trace_id") or ""), sanitized)
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")))
        return sanitized


class timed_event:
    """Small helper for deterministic duration measurement around a span."""

    def __init__(self, telemetry: Telemetry, started: str, completed: str, **fields: Any):
        self.telemetry = telemetry
        self.started_event = started
        self.completed_event = completed
        self.fields = fields
        self.started = 0.0

    def __enter__(self):
        self.started = time.monotonic()
        self.telemetry.event(self.started_event, **self.fields)
        return self

    def __exit__(self, exc_type, exc, _tb):
        latency = round((time.monotonic() - self.started) * 1000, 2)
        if exc is None:
            self.telemetry.event(self.completed_event, latency_ms=latency, **self.fields)
        else:
            self.telemetry.event(
                self.completed_event,
                level="ERROR",
                latency_ms=latency,
                error_type=type(exc).__name__,
                **self.fields,
            )
        return False
