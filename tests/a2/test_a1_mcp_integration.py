"""A2A: A1 runtime on Local vs MCP — same final state, backend only in trace."""
import json
import os

from agent.tooling import ScopedToolGateway, support_tool_registry

from app.contracts.incoming_request import IncomingRequest
from app.runtime.run_a1 import run_a1

CLOCK = lambda: "2026-08-07T00:00:00Z"  # noqa: E731

_DEMO = os.path.join(os.path.dirname(__file__), "..", "..", "data", "a1_demo_cases.json")


def load_demo_request(case_id: str) -> dict:
    with open(_DEMO, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    return next(c for c in cases if c["id"] == case_id)["request"]


def _local_gw():
    return ScopedToolGateway(support_tool_registry(), specialist="knowledge", backend="local")


def _mcp_gw():
    return ScopedToolGateway(support_tool_registry(), specialist="knowledge", backend="mcp")


def _events(result):
    return [e["event_type"] for e in result.trace]


def _tool_payloads(result):
    return [e["payload"] for e in result.trace if e["event_type"] == "tool_called"]


def test_clean_local_vs_mcp_same_final_state():
    req = load_demo_request("A1-DEMO-01")
    local = run_a1(IncomingRequest(**req), clock=CLOCK, tool_gateway=_local_gw())
    mcp = run_a1(IncomingRequest(**req), clock=CLOCK, tool_gateway=_mcp_gw())

    assert local.intents == mcp.intents
    assert local.selected_lanes == mcp.selected_lanes
    assert local.grounding_status.get("auto_reply_safe") == mcp.grounding_status.get("auto_reply_safe")
    assert local.authorization_status == mcp.authorization_status
    assert (local.proposed_action or {}).get("grounded") == (mcp.proposed_action or {}).get("grounded")
    # evidence semantics agree
    assert local.evidence_summary == mcp.evidence_summary
    # the ONLY allowed trace difference is the backend tag
    assert _tool_payloads(local)[0]["backend"] == "local"
    assert _tool_payloads(mcp)[0]["backend"] == "mcp"
    # and the trace still explains route -> lane -> authorization
    for ev in ("route_decided", "lane_started", "tool_called", "grounding_checked", "authorization_decided"):
        assert ev in _events(mcp)


def test_multi_mcp_two_slices_two_tool_calls_separate_evidence():
    req = load_demo_request("A1-DEMO-02")
    r = run_a1(IncomingRequest(**req), clock=CLOCK, tool_gateway=_mcp_gw())
    assert len(r.intents) == 2
    assert set(r.lane_results.keys()) == {"password_reset", "invoice_download"}
    payloads = _tool_payloads(r)
    assert len(payloads) == 2                    # two independent knowledge calls
    assert all(p["backend"] == "mcp" for p in payloads)
    pw = {e["doc_id"] for e in r.lane_results["password_reset"]["evidence"]}
    inv = {e["doc_id"] for e in r.lane_results["invoice_download"]["evidence"]}
    assert pw and inv and pw.isdisjoint(inv)     # separate evidence refs
    assert r.authorization_status == "AUTO_REPLY"


def test_high_risk_mcp_never_contacts_mcp():
    req = load_demo_request("A1-DEMO-03")
    gw = _mcp_gw()

    def _boom(*_a, **_k):
        raise AssertionError("MCP must not be contacted for an early-stopped request")

    gw._gateway.adapter.execute = _boom  # private access: prove 0 subprocess/tool contact
    r = run_a1(IncomingRequest(**req), clock=CLOCK, tool_gateway=gw)
    assert r.authorization_status == "ESCALATE_L2"
    assert "tool_called" not in _events(r)
    assert "lane_started" not in _events(r)
    assert r.risk_signals.get("sla_signal") is True
