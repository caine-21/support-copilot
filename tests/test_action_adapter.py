"""MockTicketActionAdapter contract tests — records, never calls external systems."""
from __future__ import annotations

from service.action_adapter import MockTicketActionAdapter


def test_create_reply_records_and_returns_synthetic_result():
    log = []
    adapter = MockTicketActionAdapter(recorder=lambda ev: log.append(ev))
    result = adapter.create_reply(
        ticket_id="T-1", draft="hello", evidence=[{"doc_id": "FAQ-x"}]
    )
    assert result["status"] == "sent_mock"
    assert result["message_id"].startswith("mock-msg-")
    assert len(adapter.executed) == 1
    assert len(log) == 1
    assert log[0]["action"] == "create_reply"
    assert log[0]["evidence_refs"] == ["FAQ-x"]


def test_create_escalation_records():
    adapter = MockTicketActionAdapter()
    result = adapter.create_escalation(
        ticket_id="T-2", level="ESCALATE_L2", reason="sla breach", evidence=[]
    )
    assert result["status"] == "escalated_mock"
    assert result["ticket_ref"].startswith("ESC-")
    assert adapter.executed[0]["system"] == "mock"
