"""A3: Skill integration into the A1 runtime — trace events + regression."""
import json
import os

from agent.tooling import ToolResult, ToolStatus

from app.contracts.incoming_request import IncomingRequest
from app.runtime.run_a1 import run_a1

CLOCK = lambda: "2026-08-07T00:00:00Z"  # noqa: E731

_DEMO = os.path.join(os.path.dirname(__file__), "..", "..", "data", "a1_demo_cases.json")


def _load(case_id: str) -> dict:
    with open(_DEMO, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    return next(c for c in cases if c["id"] == case_id)["request"]


def _types(result):
    return [e["event_type"] for e in result.trace]


def _skill_payloads(result):
    return [e["payload"] for e in result.trace if e["event_type"] == "skill_selected"]


def test_clean_trace_has_skill_events_and_state_unchanged():
    r = run_a1(IncomingRequest(**_load("A1-DEMO-01")), clock=CLOCK)
    types = _types(r)
    assert "skill_selected" in types
    assert "skill_started" in types
    assert "skill_completed" in types
    sel = _skill_payloads(r)
    assert sel[0]["skill_name"] == "knowledge_lookup"
    # A1 final state unchanged
    assert r.authorization_status == "AUTO_REPLY"
    assert r.evidence_summary == {"count": 1, "doc_ids": ["FAQ-billing-01"]}
    assert r.grounding_status.get("auto_reply_safe") is True
    assert r.selected_lanes == ["support", "knowledge"]


def test_multi_has_two_skill_executions_with_separate_intents():
    r = run_a1(IncomingRequest(**_load("A1-DEMO-02")), clock=CLOCK)
    sel = _skill_payloads(r)
    assert len(sel) == 2  # two intent slices -> two skill executions
    assert {s["intent"] for s in sel} == {"password_reset", "invoice_download"}
    # evidence still separated per intent
    pw = {e["doc_id"] for e in r.lane_results["password_reset"]["evidence"]}
    inv = {e["doc_id"] for e in r.lane_results["invoice_download"]["evidence"]}
    assert pw.isdisjoint(inv)


def test_high_risk_zero_skill_and_l2():
    r = run_a1(IncomingRequest(**_load("A1-DEMO-03")), clock=CLOCK)
    assert "skill_selected" not in _types(r)
    assert "tool_called" not in _types(r)
    assert r.authorization_status == "ESCALATE_L2"


def test_mcp_failure_still_non_auto():
    class _BrokenGateway:
        def execute(self, *_a, **_k):
            return ToolResult(status=ToolStatus.ERROR, data=None,
                              error_code="mcp_tool_error", retryable=True)

    r = run_a1(IncomingRequest(**_load("A1-DEMO-01")), clock=CLOCK,
               tool_gateway=_BrokenGateway())
    assert r.authorization_status != "AUTO_REPLY"
    # knowledge lane shows the skill failed, not a fake success
    statuses = [v["knowledge_status"] for v in r.lane_results.values()]
    assert all(s == "error" for s in statuses)


def test_specialist_result_carries_skill_metadata():
    from agent.tooling import ScopedToolGateway, support_tool_registry

    from app.specialists.contracts import KnowledgeSpecialistInput, SpecialistStatus
    from app.specialists.knowledge_specialist import run_knowledge_specialist

    gw = ScopedToolGateway(support_tool_registry(), specialist="knowledge")
    k = run_knowledge_specialist(
        KnowledgeSpecialistInput(
            request_id="r", query="How do I download my invoice?",
            intent="invoice_download", top_k=3),
        gateway=gw,
    )
    assert k.skill_name == "knowledge_lookup"
    assert k.skill_status == "success"
    assert k.status is SpecialistStatus.SUCCESS
