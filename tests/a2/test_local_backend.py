"""A2A: Local backend — 4 read tools happy path + errors in ToolResult envelope."""
import pytest

from agent.tooling import (
    ToolGateway,
    ToolRuntime,
    ToolStatus,
    support_tool_registry,
)
from service.domain import ReviewStatus, TicketRecord, WorkflowStatus


def _seed_ticket(db_path) -> None:
    from service.repository import TicketRepository

    now = "2026-08-07T00:00:00Z"
    rec = TicketRecord(
        ticket_id="T-SEED",
        request_payload={},
        normalized_input="seed",
        workflow_status=WorkflowStatus.CREATED,
        review_status=ReviewStatus.NOT_REQUIRED,
        created_at=now,
        updated_at=now,
    )
    repo = TicketRepository(db_path=str(db_path))
    repo.save_ticket(rec)
    repo.close()


def _gateway():
    return ToolGateway(support_tool_registry(), backend="local")


def test_local_all_four_happy_path(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _seed_ticket(db)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    gw = _gateway()
    rt = ToolRuntime(user_id="u-1", ticket_text="x")

    r = gw.execute("c1", "search_knowledge_base", {"query": "download my invoice", "top_k": 2}, rt, turn_index=0)
    assert r.status is ToolStatus.SUCCESS
    assert r.data

    r = gw.execute("c1", "get_ticket", {"ticket_id": "T-SEED"}, rt, turn_index=0)
    assert r.status is ToolStatus.SUCCESS
    assert r.data.get("ticket_id") == "T-SEED"

    r = gw.execute("c1", "get_customer_context", {"customer_context": {"plan": "team"}}, rt, turn_index=0)
    assert r.status is ToolStatus.SUCCESS

    r = gw.execute("c1", "get_ticket_history", {"user_id": "u-1"}, rt, turn_index=0)
    assert r.status is ToolStatus.SUCCESS


def test_local_get_ticket_not_found(tmp_path, monkeypatch):
    db = tmp_path / "tickets.db"
    _seed_ticket(db)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    r = _gateway().execute("c1", "get_ticket", {"ticket_id": "T-NOPE"},
                           ToolRuntime(user_id="u", ticket_text=""), turn_index=0)
    assert r.status is ToolStatus.NOT_FOUND
    assert r.error_code == "ticket_not_found"


def test_local_invalid_args_returns_envelope():
    r = _gateway().execute("c1", "get_ticket", {"ticket_id": ""},
                           ToolRuntime(user_id="u", ticket_text=""), turn_index=0)
    assert r.status is ToolStatus.INVALID_ARGUMENTS
    assert r.error_code == "invalid_tool_arguments"


def test_local_unregistered_tool_returns_envelope():
    r = _gateway().execute("c1", "not_a_tool", {},
                           ToolRuntime(user_id="u", ticket_text=""), turn_index=0)
    assert r.status is ToolStatus.NOT_FOUND
    assert r.error_code == "tool_not_registered"


def test_local_repository_error_returns_envelope(tmp_path):
    # A DB path whose parent is an existing FILE cannot be created -> ERROR envelope,
    # never a raised domain/transport exception.
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    import os
    os.environ["SUPPORT_DB_PATH"] = str(blocker / "sub" / "x.db")
    try:
        r = _gateway().execute("c1", "get_ticket", {"ticket_id": "T-1"},
                               ToolRuntime(user_id="u", ticket_text=""), turn_index=0)
    finally:
        os.environ.pop("SUPPORT_DB_PATH", None)
    assert r.status is ToolStatus.ERROR
    assert r.error_code == "ticket_repository_error"
