"""A3: selection, context minimization, runtime + permission intersection."""
from agent.tooling import (
    ScopedToolGateway,
    ToolRuntime,
    ToolStatus,
    support_tool_registry,
)

from app.skills.contracts import SkillStatus
from app.skills.registry import SPECIALIST_CONTEXT_FIELDS, get
from app.skills.runtime import run_skill
from app.skills.selector import select_skills


def test_selector_picks_knowledge_lookup_for_known_intent():
    sel = select_skills(specialist="knowledge", intent_set=["invoice_download"])
    assert sel.selected_skills == ["knowledge_lookup"]
    assert "knowledge_lookup:applicable" in sel.reason_codes
    assert "specialist" in sel.inputs_used and "intent_set" in sel.inputs_used


def test_selector_no_skill_for_unknown_specialist():
    sel = select_skills(specialist="ghost", intent_set=["x"])
    assert sel.selected_skills == []
    assert "no_skill" in sel.reason_codes


def test_skill_context_is_minimal_subset():
    spec = get("knowledge_lookup")
    assert set(spec.required_context) <= SPECIALIST_CONTEXT_FIELDS["knowledge"]
    for forbidden in ("authorization", "executor", "idempotency", "review_status",
                      "MockTicketActionAdapter", "grounding_status", "lane_results"):
        assert forbidden not in spec.required_context


def test_knowledge_lookup_success():
    gw = ScopedToolGateway(support_tool_registry(), specialist="knowledge")
    ctx = {"request_id": "r", "query": "How do I download my invoice?",
           "intent": "invoice_download", "top_k": 3}
    result = run_skill(get("knowledge_lookup"), ctx, gw)
    assert result.status is SkillStatus.SUCCESS
    assert any(e["doc_id"] == "FAQ-billing-01" for e in result.data["evidence"])
    assert "intent_faq_selected" in result.reason_codes


def test_knowledge_lookup_error_fails_closed():
    class _RaisingGateway:
        def execute(self, *_a, **_k):
            raise RuntimeError("boom")

    ctx = {"request_id": "r", "query": "x", "intent": "invoice_download", "top_k": 3}
    result = run_skill(get("knowledge_lookup"), ctx, _RaisingGateway())
    assert result.status is SkillStatus.ERROR
    assert result.data is None or result.data == {}


def test_runtime_defense_specialist_cannot_force_beyond_capability():
    # Even if a Skill were wrongly registered, the scoped gateway enforces the
    # Specialist∩Skill intersection at runtime (defense in depth).
    gw = ScopedToolGateway(support_tool_registry(), specialist="knowledge")
    rt = ToolRuntime(user_id="u", ticket_text="x")
    r1 = gw.execute("c1", "get_ticket", {"ticket_id": "T-1"}, rt, turn_index=0)
    assert r1.status is ToolStatus.FORBIDDEN
    r2 = gw.execute("c1", "execute_approved_reply", {"ticket_id": "T-1"}, rt, turn_index=0)
    assert r2.status is ToolStatus.FORBIDDEN
    assert r2.error_code == "specialist_tool_not_allowed"
