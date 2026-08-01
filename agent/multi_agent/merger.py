from .contracts import SpecialistResult
_RISK = {"no_change": 0, "escalate_l1": 1, "escalate_l2": 2}
def _unique(values): return list(dict.fromkeys(value for value in values if value))
def merge_specialist_results(results: list[SpecialistResult]) -> dict:
    successful = [result for result in results if result.error is None]
    routes = {result.recommended_route for result in successful}
    conflicts = ["specialist_route_conflict"] if len(routes) > 1 else []
    for result in successful:
        if result.domain_leakage_flags: conflicts.append(f"{result.specialist}_domain_leakage")
        text = " ".join(result.proposed_answer_points + result.verified_facts).lower()
        if result.specialist == "billing" and any(word in text for word in ("bug", "error", "technical")): conflicts.append("billing_technical_conclusion")
        if result.specialist == "technical" and any(word in text for word in ("refund", "credit", "payment promise")): conflicts.append("technical_billing_promise")
    return {"merged_facts": _unique(item for result in successful for item in result.verified_facts), "merged_missing_information": _unique(item for result in successful for item in result.missing_information), "merged_risk_flags": _unique(item for result in results for item in result.risk_flags), "conflicts": _unique(conflicts), "shadow_recommended_route": max((result.recommended_route for result in successful), key=lambda value: _RISK[value], default="no_change")}
