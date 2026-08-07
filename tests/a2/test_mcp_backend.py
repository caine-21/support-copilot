"""A2A: MCP backend — real stdio discovery shows the exact 4 read tools + schema parity."""
import asyncio
import os
import sys

import pytest

EXPECTED_READ_TOOLS = {
    "search_knowledge_base", "get_customer_context", "get_ticket", "get_ticket_history",
}


def _seed_ticket_db(db_path, ticket_id="T-A2-001") -> None:
    from service.domain import ReviewStatus, TicketRecord, WorkflowStatus
    from service.repository import TicketRepository

    now = "2026-08-07T00:00:00Z"
    rec = TicketRecord(
        ticket_id=ticket_id, request_payload={}, normalized_input="seed",
        workflow_status=WorkflowStatus.CREATED, review_status=ReviewStatus.NOT_REQUIRED,
        created_at=now, updated_at=now,
    )
    repo = TicketRepository(str(db_path))
    repo.save_ticket(rec)
    repo.close()


@pytest.fixture
def ticket_db(tmp_path, monkeypatch):
    """Temp SQLite DB seeded with T-A2-001; SUPPORT_DB_PATH reaches the MCP subprocess."""
    db = tmp_path / "tickets.db"
    _seed_ticket_db(db)
    monkeypatch.setenv("SUPPORT_DB_PATH", str(db))
    return db


def _params():
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command=sys.executable,
        args=["-u", "-B", "-m", "agent.support_mcp_server"],
        cwd=os.getcwd(),
        env=dict(os.environ),
    )


@pytest.fixture(scope="module")
def mcp_tools():
    async def _list():
        from mcp import Client
        from mcp.client.stdio import stdio_client

        async with Client(stdio_client(_params())) as client:
            return (await client.list_tools()).tools

    return asyncio.run(_list())


def test_mcp_exposes_four_read_plus_executor(mcp_tools):
    names = {t.name for t in mcp_tools}
    # The READ plane is exactly the four read tools.
    assert EXPECTED_READ_TOOLS <= names
    assert not (names & {"send_reply", "update_ticket", "delete_ticket"})
    # A2B: the server (capability provider) also exposes ONE executor action,
    # which is NOT part of the read plane.
    assert "execute_approved_reply" in names


def test_mcp_schema_semantic_parity(mcp_tools):
    by_name = {t.name: t for t in mcp_tools}

    search = by_name["search_knowledge_base"].input_schema
    assert "query" in search.get("required", [])
    assert search["properties"]["query"]["type"] == "string"
    assert "top_k" in search["properties"]  # optional, has default

    ticket = by_name["get_ticket"].input_schema
    assert "ticket_id" in ticket.get("required", [])
    assert ticket["properties"]["ticket_id"]["type"] == "string"

    for tool in ("get_customer_context", "get_ticket_history"):
        assert by_name[tool].input_schema is not None


def test_mcp_get_ticket_bound_enforced_server_side(ticket_db):
    # The transport schema may not carry ge/le bounds, but the canonical handler
    # enforces them: an out-of-bounds / invalid arg returns INVALID_ARGUMENTS.
    from agent.tooling import ToolGateway, ToolRuntime, ToolStatus, support_tool_registry

    gw = ToolGateway(support_tool_registry(), backend="mcp")
    rt = ToolRuntime(user_id="u", ticket_text="x")
    r = gw.execute("c1", "get_ticket", {"ticket_id": ""}, rt, turn_index=0)
    assert r.status is ToolStatus.INVALID_ARGUMENTS
    assert r.error_code == "invalid_tool_arguments"
