"""A2A: Local vs MCP backend parity — same fixture state, same business semantics.

Every scenario runs through the REAL ToolGateway (local in-process, MCP via
fresh stdio subprocess). Compared: status, business data semantics, error_code.
Allowed to differ: transport metadata / latency / trace ids.
"""
import pytest

from agent.tooling import ToolGateway, ToolRuntime, ToolStatus, support_tool_registry


@pytest.fixture
def ticket_db(tmp_path, monkeypatch):
    """Temp SQLite DB seeded with T-A2-001; SUPPORT_DB_PATH reaches the MCP subprocess."""
    from service.domain import ReviewStatus, TicketRecord, WorkflowStatus
    from service.repository import TicketRepository

    db = tmp_path / "tickets.db"
    now = "2026-08-07T00:00:00Z"
    rec = TicketRecord(
        ticket_id="T-A2-001", request_payload={}, normalized_input="seed",
        workflow_status=WorkflowStatus.CREATED, review_status=ReviewStatus.NOT_REQUIRED,
        created_at=now, updated_at=now,
    )
    repo = TicketRepository(str(db))
    repo.save_ticket(rec)
    repo.close()
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    return db


def _local():
    return ToolGateway(support_tool_registry(), backend="local")


def _mcp():
    return ToolGateway(support_tool_registry(), backend="mcp")


def _call(gw, tool, args, rt):
    return gw.execute("c1", tool, args, rt, turn_index=0)


def _rt():
    return ToolRuntime(user_id="u-1", ticket_text="x")


def _semantic(result):
    """Business-meaningful view (drop transport fields)."""
    return {
        "status": result.status.value,
        "error_code": result.error_code,
        "data": result.data,
    }


def _assert_same_business(local, mcp):
    assert local.status is mcp.status, f"status differs: {local.status} vs {mcp.status}"
    assert local.error_code == mcp.error_code, f"error_code differs: {local.error_code} vs {mcp.error_code}"
    # data semantics: compare the meaningful projection
    assert _semantic(local) == _semantic(mcp), f"business data differs:\n{_semantic(local)}\n{_semantic(mcp)}"


def test_parity_all_four_happy_path(ticket_db):
    scenarios = [
        ("search_knowledge_base", {"query": "How do I download my invoice?", "top_k": 2}),
        ("get_customer_context", {"customer_context": {"plan": "team", "region": "eu"}}),
        ("get_ticket", {"ticket_id": "T-A2-001"}),
        ("get_ticket_history", {"user_id": "u-1"}),
    ]
    for tool, args in scenarios:
        local = _call(_local(), tool, args, _rt())
        mcp = _call(_mcp(), tool, args, _rt())
        assert local.status is ToolStatus.SUCCESS, f"{tool} local not success: {local.error_code}"
        _assert_same_business(local, mcp)
        # evidence semantics (doc_ids / source refs) agree
        assert [e.model_dump() for e in local.evidence] == [e.model_dump() for e in mcp.evidence], tool


def test_parity_get_ticket_not_found(ticket_db):
    args = {"ticket_id": "T-NOPE"}
    _assert_same_business(_call(_local(), "get_ticket", args, _rt()),
                          _call(_mcp(), "get_ticket", args, _rt()))
    # both are NOT_FOUND / ticket_not_found
    r = _call(_mcp(), "get_ticket", args, _rt())
    assert r.status is ToolStatus.NOT_FOUND
    assert r.error_code == "ticket_not_found"


def test_parity_invalid_input(ticket_db):
    args = {"ticket_id": ""}
    _assert_same_business(_call(_local(), "get_ticket", args, _rt()),
                          _call(_mcp(), "get_ticket", args, _rt()))
    r = _call(_mcp(), "get_ticket", args, _rt())
    assert r.status is ToolStatus.INVALID_ARGUMENTS
    assert r.error_code == "invalid_tool_arguments"


def test_parity_empty_kb_result():
    # Deterministic no-FAQ-coverage intent (invoice_customize has [] in the map)
    # -> NOT_FOUND / knowledge_not_found on both backends.
    args = {"query": "I want to customize my invoice", "top_k": 1}
    local = _call(_local(), "search_knowledge_base", args, _rt())
    mcp = _call(_mcp(), "search_knowledge_base", args, _rt())
    _assert_same_business(local, mcp)
    assert local.status is ToolStatus.NOT_FOUND
    assert local.error_code == "knowledge_not_found"
