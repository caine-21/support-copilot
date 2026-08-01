from __future__ import annotations
import json
from .contracts import ManagerDecision
from .context import fallback_slices, validate_slices
from .safety import safe_error
_SYSTEM = "Select zero, one, or both support specialists. JSON only. Allowed: billing, technical. Do not decide customer action. Schema: selected_specialists, detected_domains, multi_intent, reason_codes, confidence."
def _parse(raw):
    try: return json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
    except (AttributeError, json.JSONDecodeError): return {}
def deterministic_manager_fallback(context):
    intents = set(context.get("intent_set", [])) | {context.get("classification", {}).get("intent"), context.get("classification", {}).get("secondary_intent")}
    selected = []
    if intents & {"billing", "churn", "invoice_download", "payment_methods", "refund_eligibility", "plan_change", "seat_management"}: selected.append("billing")
    if intents & {"bug", "account", "sso_issue", "upload_error", "signup_issue"}: selected.append("technical")
    return {"selected_specialists": selected, "domain_slices": fallback_slices(context.get("ticket_text", ""), selected), "detected_domains": selected, "multi_intent": len(selected) == 2, "reason_codes": ["manager_fallback_used", "domain_slice_fallback_used"], "confidence": 0.5}
def decide_manager(context, runner=None):
    errors = []
    try:
        if runner is None:
            from llm import call_llm, safe_json_parse
            payload = safe_json_parse(call_llm(_SYSTEM, json.dumps(context, ensure_ascii=False)))
        else:
            payload = runner(context)
            if isinstance(payload, str):
                payload = _parse(payload)
                if not payload:
                    return ManagerDecision.model_validate(deterministic_manager_fallback(context)), [safe_error("manager", code="manager_json_invalid")]
        decision = ManagerDecision.model_validate(payload)
        accepted, slice_errors = validate_slices(context.get("ticket_text", ""), decision.selected_specialists, decision.domain_slices)
        if not decision.domain_slices: accepted = fallback_slices(context.get("ticket_text", ""), decision.selected_specialists); slice_errors.append("domain_slice_fallback_used")
        decision = ManagerDecision.model_validate({**decision.model_dump(), "domain_slices": accepted, "reason_codes": list(dict.fromkeys(decision.reason_codes + slice_errors))})
        return decision, errors
    except Exception as exc:
        errors.append(safe_error("manager", exc))
        return ManagerDecision.model_validate(deterministic_manager_fallback(context)), errors
