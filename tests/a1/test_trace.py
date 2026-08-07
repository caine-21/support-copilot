"""Structured trace: monotonic, deterministic clock, no sensitive payloads."""
from app.runtime.trace import TraceCollector

FIXED = "2026-08-07T00:00:00Z"


def test_sequence_monotonic_and_request_id_consistent():
    tc = TraceCollector("req-1", clock=lambda: FIXED)
    tc.emit("a", "x")
    tc.emit("b", "y")
    evs = tc.events()
    assert [e.sequence for e in evs] == [1, 2]
    assert all(e.request_id == "req-1" for e in evs)
    assert all(e.timestamp == FIXED for e in evs)  # injected clock -> deterministic


def test_event_ordering_preserved():
    tc = TraceCollector("r", clock=lambda: FIXED)
    tc.emit("first", "a")
    tc.emit("second", "b")
    assert [e.event_type for e in tc.events()] == ["first", "second"]


def test_payload_structured_not_sensitive():
    tc = TraceCollector("r", clock=lambda: FIXED)
    tc.emit("tool_called", "knowledge",
            payload={"tool": "search_knowledge_base", "intent": "invoice_download", "status": "success"})
    e = tc.events()[0]
    assert e.payload["tool"] == "search_knowledge_base"
    assert "system prompt" not in str(e.payload).lower()
    assert "api_key" not in str(e.payload).lower()
