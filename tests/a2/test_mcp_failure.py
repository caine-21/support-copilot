"""A2A: MCP failure must be fail-safe — never degrades into an empty success
and never unlocks AUTO_REPLY."""
import json
import os

from agent.tooling import (
    MCPToolAdapter,
    SearchKnowledgeArgs,
    ToolResult,
    ToolStatus,
    support_tool_registry,
)

from app.contracts.incoming_request import IncomingRequest
from app.runtime.run_a1 import run_a1

CLOCK = lambda: "2026-08-07T00:00:00Z"  # noqa: E731

_DEMO = os.path.join(os.path.dirname(__file__), "..", "..", "data", "a1_demo_cases.json")


def load_demo_request(case_id: str) -> dict:
    with open(_DEMO, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    return next(c for c in cases if c["id"] == case_id)["request"]


def test_transport_failure_is_error_not_empty_success():
    # A server that cannot spawn must return ERROR (mcp_connection_*), never
    # a SUCCESS-with-empty-data that could be misread as "no evidence".
    adapter = MCPToolAdapter(command="definitely-not-a-real-exe",
                             args=["-B", "-m", "agent.support_mcp_server"])
    result = adapter.execute(support_tool_registry()["search_knowledge_base"],
                             SearchKnowledgeArgs(query="x", top_k=1), None, 5.0)
    assert result.status is ToolStatus.ERROR
    assert result.error_code.startswith("mcp_connection_")


def test_timeout_keeps_timeout_semantics():
    class _TimeoutGateway:
        def execute(self, *_a, **_k):
            return ToolResult(status=ToolStatus.TIMEOUT, data=None, error_code="mcp_timeout", retryable=True)

    r = run_a1(IncomingRequest(**load_demo_request("A1-DEMO-01")), clock=CLOCK,
               tool_gateway=_TimeoutGateway())
    assert r.authorization_status != "AUTO_REPLY"
    # Knowledge lane shows a failure, not an empty success
    statuses = [v["knowledge_status"] for v in r.lane_results.values()]
    assert all(s == "error" for s in statuses)


def test_mcp_failure_chain_blocks_auto():
    # server unavailable -> tool ERROR -> specialist ERROR -> no positive
    # evidence -> grounding fail-closed -> authorization != AUTO_REPLY.
    class _BrokenGateway:
        def execute(self, *_a, **_k):
            return ToolResult(status=ToolStatus.ERROR, data=None, error_code="mcp_tool_error", retryable=True)

    r = run_a1(IncomingRequest(**load_demo_request("A1-DEMO-01")), clock=CLOCK,
               tool_gateway=_BrokenGateway())
    assert r.authorization_status != "AUTO_REPLY"
    assert r.grounding_status.get("auto_reply_safe") is not True


def test_malformed_result_fails_closed():
    class _MalformedGateway:
        def execute(self, *_a, **_k):
            # A result whose status is not success must not be treated as evidence.
            return ToolResult(status=ToolStatus.ERROR, data=[{"doc_id": "FAQ-billing-01"}],
                              error_code="malformed")

    r = run_a1(IncomingRequest(**load_demo_request("A1-DEMO-01")), clock=CLOCK,
               tool_gateway=_MalformedGateway())
    assert r.authorization_status != "AUTO_REPLY"
