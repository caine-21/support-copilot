from agent.agent_loop import run_agent
from agent.multi_agent.shadow import MultiAgentShadowRunner
from conftest import manager, specialist


class FakeTool:
    def __init__(self, value): self.value = value
    def execute(self, _): return {"success": True, "data": self.value}


def registry():
    return {
        "classify_intent": FakeTool({"intent": "billing", "confidence": .9, "secondary_intent": None}),
        "kb_search": FakeTool([{"doc_id": "FAQ-billing-01", "snippet": "Download invoices from Billing.", "score": 1.0}]),
        "history_lookup": FakeTool({"past_tickets": [], "ticket_count": 0}),
        "tone_check": FakeTool({"tone": "neutral", "churn_risk": 0, "churn_signals": [], "urgency": "low"}),
        "draft_reply": FakeTool({"reply": "Download invoices from Billing.", "grounded": True, "kb_used": ["FAQ-billing-01"], "gaps": "", "grounding_check": {"grounding_ratio": 1, "auto_reply_safe": True, "ungrounded_claims": []}}),
    }


def test_off_and_shadow_leave_baseline_unchanged():
    off = run_agent("How do I download an invoice?", registry=registry(), no_service=True)
    shadow = run_agent("How do I download an invoice?", registry=registry(), no_service=True, multi_agent_mode="shadow", multi_agent_runner=MultiAgentShadowRunner(manager(["billing"]), specialist))
    assert "multi_agent_shadow" not in off
    assert shadow["action"] == off["action"]
    assert shadow["grounding_check"] == off["grounding_check"]
    assert shadow["draft_reply"] == off["draft_reply"]
    assert shadow["multi_agent_shadow"]["baseline_action"] == off["action"]


def test_early_l2_skips_manager():
    calls = []
    runner = MultiAgentShadowRunner(lambda c: calls.append(c) or manager([])(c), specialist)
    result = run_agent("Our SLA has been breached", registry=registry(), no_service=True, multi_agent_mode="shadow", multi_agent_runner=runner)
    assert result["action"] == "ESCALATE_L2" and result["multi_agent_shadow"]["skip_reason"] == "early_l2" and not calls
