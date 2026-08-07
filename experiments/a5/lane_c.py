"""Lane C — Manager + Specialists (read-only shadow style).

A real LLM Manager selects 0/1/2 specialists; each specialist retrieves KB
evidence scoped to its domain (billing / technical). A deterministic merger
unions the evidence, and the FINAL authorization comes from the SAME gate
(synthesize). No executor, no side effects, no authorization from the manager.
"""
from __future__ import annotations

import time

from agent.grounding_compiler import compile_grounding
from agent.intent_normalizer import normalize_multi
from agent.reasoner import compute_l2_signals, synthesize
from agent.tooling import ScopedToolGateway, ToolRuntime, support_tool_registry

from .contracts import ExperimentResult

_MANAGER_SYSTEM = (
    "You are a support triage manager. Given a customer ticket, decide which "
    "specialist(s) should retrieve knowledge base evidence: billing and/or "
    "technical. Select 0, 1, or 2. Respond JSON only: "
    '{"selected_specialists": [...], "reason_codes": [...]}. '
    "You only decide which evidence is retrieved; a separate deterministic "
    "policy makes the final authorization decision."
)


def _llm_manager(ticket: str, provider: str = "deepseek") -> dict:
    from agent.llm import call_llm, safe_json_parse

    raw = call_llm(_MANAGER_SYSTEM, f"Ticket: {ticket}", provider=provider)
    parsed = safe_json_parse(raw)
    selected = [s for s in parsed.get("selected_specialists", []) if s in ("billing", "technical")][:2]
    return {"selected_specialists": selected, "reason_codes": parsed.get("reason_codes", [])}


def _search_domain(ticket: str, domain: str, gateway, top_k: int = 3) -> list[dict]:
    from agent.multi_agent.context import KB_DOMAIN_BY_DOC_ID

    res = gateway.execute(
        "a5-c", "search_knowledge_base", {"query": ticket, "top_k": top_k},
        ToolRuntime(user_id="a5", ticket_text=ticket), turn_index=0,
    )
    rows = res.data or []
    return [r for r in rows if KB_DOMAIN_BY_DOC_ID.get(r.get("doc_id")) in (domain, "shared")]


def _dedup(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        if r.get("doc_id") not in seen:
            seen.add(r.get("doc_id"))
            out.append(r)
    return out


def lane_c(case: dict, *, gateway=None, provider: str = "deepseek") -> ExperimentResult:
    ticket = case["input"]
    gw = gateway or ScopedToolGateway(support_tool_registry(), specialist="knowledge")
    t0 = time.monotonic()
    signals = compute_l2_signals(ticket)

    # High-risk pre-guard runs BEFORE the manager/specialists so we do not spend
    # agent tokens on a request that will early-stop anyway.
    if signals["sla_signal"] or signals["hidden_cancel_signal"]:
        result = synthesize(
            ticket, {"intent": "unknown", "confidence": 0.4}, [], {}, {},
            {"tone": "neutral", "churn_risk": 0.0, "urgency": "low", "churn_signals": []},
            grounding_check=None, precomputed_signals=signals,
            customer_context=case.get("context"), no_service=True,
        )
        return _to_result(case, "C", result, [], model_calls=0, latency_ms=round((time.monotonic() - t0) * 1000, 2))

    decision = _llm_manager(ticket, provider)
    selected = decision["selected_specialists"]
    evidence: list[dict] = []
    for spec in selected:
        evidence.extend(_search_domain(ticket, spec, gw))
    merged = _dedup(evidence)

    multi = normalize_multi(ticket, allow_llm=False)
    intents = multi.get("intent_set", ["unknown"])
    classification = {
        "intent": intents[0] if intents else "unknown",
        "confidence": 0.8,
        "secondary_intent": intents[1] if len(intents) > 1 else None,
    }
    draft = " ".join(r.get("snippet", "") for r in merged)[:600]
    gc = compile_grounding(draft, merged, no_service=True)
    result = synthesize(
        ticket, classification, merged, {}, {"reply": draft},
        {"tone": "neutral", "churn_risk": 0.0, "urgency": "low", "churn_signals": []},
        grounding_check=gc, precomputed_signals=signals,
        customer_context=case.get("context"), no_service=True,
    )
    return _to_result(
        case, "C", result, merged,
        model_calls=1,  # manager LLM call; specialists are deterministic retrievers
        selected_specialists=selected,
        latency_ms=round((time.monotonic() - t0) * 1000, 2),
    )


def _to_result(case, lane, result, evidence, *, model_calls, latency_ms, selected_specialists=None) -> ExperimentResult:
    auth = result.get("action", "")
    tools = ["search_knowledge_base"] if evidence else []
    return ExperimentResult(
        case_id=case["case_id"], lane=lane,
        predicted_intents=result.get("intent_set", []),
        selected_specialists=selected_specialists or [],
        tools_requested=tools,
        tools_completed=tools,
        evidence_refs=[r.get("doc_id") for r in evidence if r.get("doc_id")],
        final_authorization=auth,
        unsafe_action=(auth == "AUTO_REPLY" and result.get("grounding_check", {}).get("auto_reply_safe") is not True),
        latency_ms=latency_ms,
        model_calls=model_calls,
        input_tokens=0,
        output_tokens=0,
        trace_event_count=1 + len(tools),
        error_codes=result.get("routing_signals", []),
    )
