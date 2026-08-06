"""Side-effect adapter contract + mock implementation.

Every irreversible/ticketing action goes through TicketActionAdapter so the
service layer never touches an external system. The default implementation
(MockTicketActionAdapter) records the action through a recorder callback and
returns a synthetic result — no Zendesk / Intercom / email is ever called.

The adapter is deliberately dumb: it does NOT decide whether to act. The engine
applies the decision gate + idempotency check before invoking it.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Optional, Protocol

# recorder: called with an action event dict after a successful mock execution
ActionRecorder = Callable[[dict[str, Any]], None]


class TicketActionAdapter(Protocol):
    name: str

    def create_reply(
        self, *, ticket_id: str, draft: str, evidence: list[Any]
    ) -> dict[str, Any]: ...

    def create_escalation(
        self,
        *,
        ticket_id: str,
        level: str,
        reason: str,
        evidence: list[Any],
    ) -> dict[str, Any]: ...


class MockTicketActionAdapter:
    """Records actions; never contacts an external customer-support system."""

    name = "mock"

    def __init__(self, recorder: Optional[ActionRecorder] = None):
        self._recorder = recorder
        # in-memory action log (belt-and-braces; persistence lives in the repo)
        self.executed: list[dict[str, Any]] = []

    def create_reply(
        self, *, ticket_id: str, draft: str, evidence: list[Any]
    ) -> dict[str, Any]:
        event = {
            "action": "create_reply",
            "ticket_id": ticket_id,
            "message_id": f"mock-msg-{uuid.uuid4().hex[:12]}",
            "draft_preview": draft[:120],
            "evidence_refs": [e.get("doc_id") for e in (evidence or []) if isinstance(e, dict)],
            "system": "mock",  # never real
        }
        self.executed.append(event)
        if self._recorder is not None:
            self._recorder(event)
        return {"status": "sent_mock", "message_id": event["message_id"]}

    def create_escalation(
        self,
        *,
        ticket_id: str,
        level: str,
        reason: str,
        evidence: list[Any],
    ) -> dict[str, Any]:
        event = {
            "action": "create_escalation",
            "ticket_id": ticket_id,
            "level": level,
            "ticket_ref": f"ESC-{uuid.uuid4().hex[:10].upper()}",
            "reason_preview": reason[:120],
            "system": "mock",  # never real
        }
        self.executed.append(event)
        if self._recorder is not None:
            self._recorder(event)
        return {"status": "escalated_mock", "ticket_ref": event["ticket_ref"]}
