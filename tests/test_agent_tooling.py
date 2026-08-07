from types import SimpleNamespace
import asyncio
import os
import sys
import time
from typing import TypedDict

import pytest

from agent.function_calling import NativeFunctionCallingAdapter, ScriptedModelAdapter
from agent.memory import AgentMemory
from agent.tool_eval import evaluate_tool_runs
from agent.tool_loop import run_tool_loop
from agent.tooling import CustomerContextArgs, SearchKnowledgeArgs, ToolDefinition, ToolGateway, ToolPermission, ToolResult, ToolRuntime, ToolStatus


def _safe_context():
    return {"fields": {
        name: {"value": value, "status": "known", "source": "test", "updated_at": "2026-08-02", "allowed_for_auto_reply": True}
        for name, value in {
            "plan": "enterprise", "region": "US", "role": "admin",
            "permissions": ["manage_billing", "manage_members", "configure_security"],
            "contract_status": "active", "account_status": "active",
        }.items()
    }}


def test_gateway_validates_and_blocks_unknown_tool():
    gateway = ToolGateway(backend="local")
    runtime = ToolRuntime(user_id="U-1", ticket_text="invoice")
    assert gateway.execute("c1", "missing", {}, runtime, 1).status is ToolStatus.NOT_FOUND
    assert gateway.execute("c2", "search_knowledge_base", {"top_k": 3}, runtime, 1).status is ToolStatus.INVALID_ARGUMENTS


def test_native_adapter_reads_provider_tool_calls_without_text_json_emulation():
    call = SimpleNamespace(id="native-1", function=SimpleNamespace(name="search_knowledge_base", arguments='{"query":"invoice"}'))
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))])
    router = SimpleNamespace(call_with_tools=lambda **_: response)
    turn = NativeFunctionCallingAdapter(router=router).next_turn([], [])
    assert turn.tool_calls[0].name == "search_knowledge_base"
    assert turn.tool_calls[0].arguments == {"query": "invoice"}


def test_tool_loop_two_step_evidence_and_final_proposal():
    model = ScriptedModelAdapter([
        {"tool_calls": [{"call_id": "kb-1", "name": "search_knowledge_base", "arguments": {"query": "How do I download an invoice?"}}]},
        {"tool_calls": [{"call_id": "ctx-1", "name": "get_customer_context", "arguments": {"customer_context": _safe_context()}}]},
        {"content": "You can download invoices from Billing settings."},
    ])
    result, state = run_tool_loop("How do I download an invoice?", "T-tool", "U-tool", AgentMemory(), _safe_context(), model=model)
    assert state.stop_reason == "final_output"
    assert [item["tool_name"] for item in state.tool_executions] == ["search_knowledge_base", "get_customer_context"]
    assert state.collected_evidence and result["tool_run"]["final_proposal"]
    assert any(message["role"] == "tool" for message in model.seen_messages[-1])


def test_duplicate_and_pre_guard_never_auto_reply():
    duplicate = ScriptedModelAdapter([
        {"tool_calls": [{"call_id": "a", "name": "get_customer_context", "arguments": {"customer_context": _safe_context()}}]},
        {"tool_calls": [{"call_id": "b", "name": "get_customer_context", "arguments": {"customer_context": _safe_context()}}]},
    ])
    _, state = run_tool_loop("Need invoice help", "T-dup", "U", AgentMemory(), model=duplicate)
    assert state.stop_reason == "duplicate_tool_call"
    high_risk, high_state = run_tool_loop("Our SLA has been breached", "T-risk", "U", AgentMemory(), model=duplicate)
    assert high_state.stop_reason == "pre_guard_escalation"
    assert high_risk["action"] == "ESCALATE_L2"


def test_mcp_backend_matches_local_contract():
    runtime = ToolRuntime(user_id="U", ticket_text="invoice")
    args = {"query": "How do I download an invoice?", "top_k": 1}
    local = ToolGateway(backend="local").execute("local", "search_knowledge_base", args, runtime, 1)
    mcp = ToolGateway(backend="mcp", tool_timeout_seconds=10).execute("mcp", "search_knowledge_base", args, runtime, 1)
    assert local.status == mcp.status == ToolStatus.SUCCESS
    assert local.evidence and mcp.evidence


@pytest.mark.anyio
async def test_mcp_v2_in_memory_contract():
    from agent.support_mcp_server import mcp
    from mcp import Client
    client = Client(mcp, raise_exceptions=True)
    await asyncio.wait_for(client.__aenter__(), timeout=3)  # phase 1: Client enter
    try:
        tools = await asyncio.wait_for(client.list_tools(), timeout=3)  # phase 2: list_tools
        assert "search_knowledge_base" in {tool.name for tool in tools.tools}
        kb_tool = next(tool for tool in tools.tools if tool.name == "search_knowledge_base")
        assert {"status", "data", "evidence", "error_code", "retryable"} <= set(kb_tool.output_schema["properties"])
        result = await asyncio.wait_for(client.call_tool("search_knowledge_base", {"query": "invoice", "top_k": 1}), timeout=3)  # phase 3: call_tool
        assert result.is_error is False
        assert result.structured_content["status"] == "success"
        assert result.structured_content["evidence"][0]["source_type"] == "knowledge_base"
    finally:
        await asyncio.wait_for(client.__aexit__(None, None, None), timeout=3)  # phase 4: Client exit


class _PingResult(TypedDict):
    value: str


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_v2_minimal_in_memory_ping():
    """Isolation test: no project server or domain handler is imported."""
    from mcp import Client
    from mcp.server import MCPServer

    server = MCPServer("minimal-ping")

    @server.tool(structured_output=True)
    def ping() -> _PingResult:
        return {"value": "pong"}

    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("ping", {})
        assert result.is_error is False
        assert result.structured_content == {"value": "pong"}


@pytest.mark.anyio
async def test_mcp_v2_stdio_three_read_tools_and_clean_exit():
    """Real child-process smoke: every protocol phase has its own deadline."""
    from agent.support_mcp_server import MCPToolResultDTO
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    project_root = os.path.dirname(os.path.dirname(__file__))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-u", "-B", "-m", "agent.support_mcp_server"],
        cwd=project_root,
        env={"PYTHONPATH": project_root, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    client = Client(stdio_client(params), raise_exceptions=True)
    # Evidence-based startup deadline (scripts/diagnose_mcp_stdio.py): MCP
    # initialize is cold-import bound, p95 ~10.6s / max ~11.7s on this Windows
    # host. 12s was sitting on the tail and flaked under load; 30s matches the
    # MCPToolAdapter startup deadline. list_tools / call_tool timeouts below
    # are the post-startup tool-execution phase and stay tight.
    await asyncio.wait_for(client.__aenter__(), timeout=30)  # enter / child start
    try:
        listed = await asyncio.wait_for(client.list_tools(), timeout=4)
        by_name = {tool.name: tool for tool in listed.tools}
        assert {"search_knowledge_base", "get_customer_context", "get_ticket_history"} <= set(by_name)
        for tool in by_name.values():
            assert {"status", "data", "evidence", "error_code", "retryable"} <= set(tool.output_schema["properties"])
        calls = [
            ("search_knowledge_base", {"query": "invoice", "top_k": 1}),
            ("get_customer_context", {"customer_context": _safe_context()}),
            ("get_ticket_history", {"user_id": "U-stdio"}),
        ]
        for name, arguments in calls:
            response = await asyncio.wait_for(client.call_tool(name, arguments), timeout=5)
            assert response.is_error is False
            dto = MCPToolResultDTO.model_validate(response.structured_content)
            assert dto.status == "success"
            assert dto.evidence
    finally:
        await asyncio.wait_for(client.__aexit__(None, None, None), timeout=6)  # pipes/process close


def test_local_timeout_does_not_wait_for_read_tool():
    def slow(_, __):
        time.sleep(0.5)
        return ToolResult(status=ToolStatus.SUCCESS)
    registry = {"slow": ToolDefinition("slow", "test-only slow read", SearchKnowledgeArgs, ToolPermission.READ, slow)}
    started = time.monotonic()
    result = ToolGateway(registry, tool_timeout_seconds=0.03).execute(
        "slow-1", "slow", {"query": "invoice"}, ToolRuntime(user_id="U", ticket_text="x"), 1
    )
    assert result.status is ToolStatus.TIMEOUT
    assert time.monotonic() - started < 0.2


def test_tool_eval_reports_contract_metrics_and_evidence_boundary():
    report = evaluate_tool_runs([{
        "tool_selection_correct": True, "arguments_valid": True,
        "multi_step_success": True, "terminated": True,
        "contract_parity": True, "grounded_final": True, "tool_calls": 2,
    }])
    assert report["unsafe_action_count"] == 0
    assert report["average_tool_calls"] == 2
    assert "not real-model accuracy" in report["evidence_boundary"]
