"""A2B: approval-gated MCP mock action.

Invariant: Agent proposal != Human approval != Execution authorization.
A caller can never pass approval/content through tool arguments; the server
reads persisted approval, evidence and idempotency.
"""
import json
import os

import pytest
from pydantic import ValidationError

from agent.tooling import (
    ExecuteApprovedReplyArgs,
    ScopedToolGateway,
    ToolGateway,
    ToolRuntime,
    ToolStatus,
    execute_approved_reply,
    executor_gateway,
    executor_tool_registry,
    support_tool_registry,
    tools_for_scope,
)
from service.action_adapter import MockTicketActionAdapter
from service.domain import ActionStatus, ReviewStatus, ReviewerAction, TicketCreate
from service.engine import TicketWorkflowService
from service.repository import TicketRepository
from tests._service_helpers import make_fake_decision_fn


def _svc(db_path, **kw):
    return TicketWorkflowService(enable_ledger=False, db_path=str(db_path), **kw)


def _create_ticket(db_path, *, grounding_safe=True, draft="Approved draft content.", evidence=None):
    svc = _svc(db_path, decision_fn=make_fake_decision_fn(
        grounding_safe=grounding_safe, draft=draft, kb=evidence))
    svc.create_ticket(TicketCreate(ticket_text="How do I reset my password?", ticket_id="T-A2B-001"))
    return svc


def _persist_approval(db_path, review_status=ReviewStatus.APPROVED,
                      reviewer_action=ReviewerAction.APPROVED.value):
    from service.engine import TicketWorkflowService

    repo = TicketRepository(str(db_path))
    ticket = repo.get_ticket("T-A2B-001")
    ticket.review_status = review_status
    ticket.reviewer_action = reviewer_action
    if review_status == ReviewStatus.APPROVED:
        # A4: a bound approved payload is required before execution is possible.
        payload = ticket.draft_response or ""
        ticket.approved_payload = payload
        ticket.approved_payload_hash = TicketWorkflowService._payload_hash(payload)
        ticket.action_status = ActionStatus.READY_FOR_EXECUTION.value
    repo.update_ticket(ticket)
    repo.close()
    return ticket


def _actions(db_path):
    repo = TicketRepository(str(db_path))
    acts = repo.list_actions("T-A2B-001")
    repo.close()
    return acts


def _rt():
    return ToolRuntime(user_id="u-1", ticket_text="x")


@pytest.fixture(autouse=True)
def _enable_mock_executor_for_contract_tests(monkeypatch):
    """Positive execution contracts use the built-in mock adapter only."""
    monkeypatch.setenv("ENABLE_EXECUTOR", "true")


def test_executor_disabled_fails_closed(monkeypatch):
    monkeypatch.setenv("ENABLE_EXECUTOR", "false")
    result = execute_approved_reply(ExecuteApprovedReplyArgs(ticket_id="T-A2B-001"), _rt())
    assert result.status is ToolStatus.FORBIDDEN
    assert result.error_code == "executor_disabled"


# ── contract: no self-approval fields ───────────────────────────────────────

def test_args_schema_has_no_self_approval_fields():
    a = ExecuteApprovedReplyArgs(ticket_id="T-1")
    assert a.ticket_id == "T-1"
    assert not hasattr(a, "approved")
    with pytest.raises(ValidationError):
        ExecuteApprovedReplyArgs(ticket_id="T-1", approved=True)
    with pytest.raises(ValidationError):
        ExecuteApprovedReplyArgs(ticket_id="T-1", review_status="approved")
    with pytest.raises(ValidationError):
        ExecuteApprovedReplyArgs(ticket_id="T-1", reply_text="injected")
    with pytest.raises(ValidationError):
        ExecuteApprovedReplyArgs(ticket_id="T-1", force=True)


# ── capability scopes ────────────────────────────────────────────────────────

def test_executor_scope_discovers_only_action():
    assert {d.name for d in tools_for_scope("executor")} == {"execute_approved_reply"}
    # The read registry never contains the side-effect tool.
    assert "execute_approved_reply" not in support_tool_registry()


def test_specialists_cannot_discover_or_force_execute():
    for specialist in ("knowledge", "support"):
        gw = ScopedToolGateway(support_tool_registry(), specialist=specialist)
        assert "execute_approved_reply" not in {d.name for d in gw.available_tools()}
        res = gw.execute("c1", "execute_approved_reply", {"ticket_id": "T-A2B-001"}, _rt(), turn_index=0)
        assert res.status is ToolStatus.FORBIDDEN
        assert res.error_code == "specialist_tool_not_allowed"


# ── server-side approval boundary (defense in depth) ────────────────────────

def test_mcp_without_approval_approval_required(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _create_ticket(db)  # review_status stays PENDING
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    gw = executor_gateway("mcp")
    res = gw.execute("c1", "execute_approved_reply", {"ticket_id": "T-A2B-001"}, _rt(), turn_index=0)
    assert res.status is ToolStatus.FORBIDDEN
    assert res.error_code == "approval_required"
    assert _actions(db) == []  # adapter never called


def test_mcp_extra_approved_field_rejected(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _create_ticket(db)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    gw = executor_gateway("mcp")
    res = gw.execute("c1", "execute_approved_reply",
                     {"ticket_id": "T-A2B-001", "approved": True}, _rt(), turn_index=0)
    assert res.status is ToolStatus.INVALID_ARGUMENTS
    assert res.error_code == "invalid_tool_arguments"
    assert _actions(db) == []


def test_mcp_approved_happy_path_executes_persisted_draft(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _create_ticket(db, draft="APPROVED-DRAFT-42")
    _persist_approval(db)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    gw = executor_gateway("mcp")
    res = gw.execute("c1", "execute_approved_reply", {"ticket_id": "T-A2B-001"}, _rt(), turn_index=0)
    assert res.status is ToolStatus.SUCCESS
    actions = _actions(db)
    assert len(actions) == 1
    assert actions[0].status.value == "executed"
    assert "sent_mock" in json.dumps(actions[0].result or {})


def test_executed_content_is_persisted_draft_service_level(tmp_path):
    # Direct proof: the adapter receives the PERSISTED approved draft, not
    # anything the caller supplied (service-level with a recording adapter).
    db = tmp_path / "tickets.db"
    _create_ticket(db, draft="APPROVED-DRAFT-42")
    _persist_approval(db)
    recorder = []
    adapter = MockTicketActionAdapter(recorder=lambda ev: recorder.append(ev))
    svc = _svc(db, decision_fn=make_fake_decision_fn(), adapter=adapter)
    outcome = svc.execute_approved_reply("T-A2B-001")
    assert outcome.action is not None
    assert recorder and recorder[0]["draft_preview"] == "APPROVED-DRAFT-42"


def test_duplicate_is_idempotent(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _create_ticket(db)
    _persist_approval(db)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    gw = executor_gateway("mcp")
    r1 = gw.execute("c1", "execute_approved_reply", {"ticket_id": "T-A2B-001"}, _rt(), turn_index=0)
    r2 = gw.execute("c2", "execute_approved_reply", {"ticket_id": "T-A2B-001"}, _rt(), turn_index=0)
    assert r1.status is ToolStatus.SUCCESS and r2.status is ToolStatus.SUCCESS
    assert "already executed" in (r2.data or {}).get("message", "")
    # Adapter executed once across both calls (repo-level idempotency).
    assert len(_actions(db)) == 1


def test_unsafe_grounding_blocks_even_with_approval(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _create_ticket(db, grounding_safe=False)
    _persist_approval(db)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    gw = executor_gateway("mcp")
    res = gw.execute("c1", "execute_approved_reply", {"ticket_id": "T-A2B-001"}, _rt(), turn_index=0)
    assert res.status is ToolStatus.FORBIDDEN
    assert res.error_code == "grounding_not_authorized"
    assert _actions(db) == []


def test_rejected_not_executable(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _create_ticket(db)
    _persist_approval(db, review_status=ReviewStatus.REJECTED,
                     reviewer_action=ReviewerAction.REJECTED.value)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    gw = executor_gateway("mcp")
    res = gw.execute("c1", "execute_approved_reply", {"ticket_id": "T-A2B-001"}, _rt(), turn_index=0)
    assert res.status is ToolStatus.FORBIDDEN
    assert res.error_code == "review_rejected"
    assert _actions(db) == []


def test_adapter_failure_recorded_not_success(tmp_path):
    db = tmp_path / "tickets.db"
    _create_ticket(db)
    _persist_approval(db)

    class _BoomAdapter:
        def create_reply(self, **_kw):
            raise RuntimeError("provider down")

    svc = _svc(db, decision_fn=make_fake_decision_fn(), adapter=_BoomAdapter())
    with pytest.raises(RuntimeError):
        svc.execute_approved_reply("T-A2B-001")
    actions = _actions(db)
    assert len(actions) == 1
    assert actions[0].status.value == "failed"   # FAILED != EXECUTED
    assert "provider down" in (actions[0].error or "")


def test_failed_action_retry_is_explicit_not_reinvoked(tmp_path):
    # Strategy B: a FAILED attempt is a terminal failure state. A second call
    # must NOT re-invoke the adapter and must NOT crash on the UNIQUE
    # idempotency key — it returns previous_execution_failed.
    from service.engine import InvalidTransition

    db = tmp_path / "tickets.db"
    _create_ticket(db)
    _persist_approval(db)
    calls = []

    class _BoomAdapter:
        def create_reply(self, **_kw):
            calls.append(1)
            raise RuntimeError("provider down")

    svc = _svc(db, decision_fn=make_fake_decision_fn(), adapter=_BoomAdapter())
    with pytest.raises(RuntimeError):
        svc.execute_approved_reply("T-A2B-001")
    assert len(calls) == 1

    with pytest.raises(InvalidTransition) as exc:
        svc.execute_approved_reply("T-A2B-001")
    assert "previous_execution_failed" in str(exc.value)
    assert len(calls) == 1  # adapter NOT re-invoked
    actions = _actions(db)
    assert len(actions) == 1 and actions[0].status.value == "failed"


def test_handler_maps_previous_execution_failed():
    from unittest import mock

    from agent.tooling import ExecuteApprovedReplyArgs, ToolStatus, execute_approved_reply
    from service.engine import InvalidTransition

    with mock.patch("service.engine.TicketWorkflowService") as MockSvc:
        MockSvc.return_value.execute_approved_reply.side_effect = \
            InvalidTransition("previous_execution_failed — manual retry required")
        res = execute_approved_reply(ExecuteApprovedReplyArgs(ticket_id="T-1"), None)
    assert res.status is ToolStatus.ERROR
    assert res.error_code == "previous_execution_failed"
