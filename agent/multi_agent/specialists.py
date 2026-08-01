from __future__ import annotations
import json
from .contracts import SpecialistResult
from .safety import safe_error
_SYSTEM = "You are a shadow-only {name} support specialist. Return JSON only. Analyse only: never execute refunds, account/plan changes, sends, or tickets. Keep verified facts limited to supplied KB and flag domain leakage."
def _parse(raw):
    try: return json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
    except (AttributeError, json.JSONDecodeError): return {}
def run_specialist(name, context, runner=None):
    try:
        if runner is None:
            from llm import call_llm, safe_json_parse
            payload = safe_json_parse(call_llm(_SYSTEM.format(name=name), json.dumps(context, ensure_ascii=False)))
        else:
            payload = runner(name, context)
            if isinstance(payload, str):
                payload = _parse(payload)
        return SpecialistResult.model_validate({**payload, "specialist": name})
    except Exception as exc:
        return SpecialistResult(specialist=name, applicable=False, confidence=0.0, error=safe_error(name, exc), risk_flags=["specialist_failure"])
