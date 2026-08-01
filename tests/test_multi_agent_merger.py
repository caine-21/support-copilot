from agent.multi_agent.contracts import SpecialistResult
from agent.multi_agent.merger import merge_specialist_results


def test_merger_deduplicates_escalates_and_detects_conflicts():
    billing = SpecialistResult(specialist="billing", applicable=True, confidence=1, verified_facts=["same", "technical error"], missing_information=["id"], risk_flags=["risk"], recommended_route="no_change")
    technical = SpecialistResult(specialist="technical", applicable=True, confidence=1, verified_facts=["same", "refund promise"], missing_information=["id"], risk_flags=["risk"], recommended_route="escalate_l2")
    merged = merge_specialist_results([billing, technical])
    assert merged["merged_facts"] == ["same", "technical error", "refund promise"]
    assert merged["shadow_recommended_route"] == "escalate_l2"
    assert {"specialist_route_conflict", "billing_technical_conclusion", "technical_billing_promise"} <= set(merged["conflicts"])
