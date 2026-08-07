"""Structured A1 trace.

Never stores sensitive full text: payloads carry refs, hashes and selected
structured fields only. timestamp is injectable for deterministic tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    event_id: str
    request_id: str
    sequence: int
    stage: str
    component: str
    event_type: str
    reason_codes: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    timestamp: str = ""


class TraceCollector:
    def __init__(self, request_id: str, *, clock: Callable[[], str] | None = None):
        self.request_id = request_id
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self._seq = 0
        self._events: list[TraceEvent] = []

    def emit(
        self,
        event_type: str,
        component: str,
        *,
        stage: str = "",
        reason_codes: list[str] | None = None,
        input_refs: list[str] | None = None,
        output_refs: list[str] | None = None,
        payload: dict | None = None,
    ) -> TraceEvent:
        self._seq += 1
        ev = TraceEvent(
            event_id=f"{self.request_id}:{self._seq}",
            request_id=self.request_id,
            sequence=self._seq,
            stage=stage,
            component=component,
            event_type=event_type,
            reason_codes=list(reason_codes or []),
            input_refs=list(input_refs or []),
            output_refs=list(output_refs or []),
            payload=dict(payload or {}),
            timestamp=self._clock(),
        )
        self._events.append(ev)
        return ev

    def events(self) -> list[TraceEvent]:
        return self._events
