"""A1 unified request runtime orchestrator.

Chain: validate -> normalize -> risk -> route -> project -> lanes -> merge
       -> grounding (legacy, fail-closed) -> authorization (legacy gate)
       -> trace.

Policy (routing thresholds, grounding, risk, AUTO/L1/L2 authorization) is
owned by the existing agent.* modules; this orchestrator only coordinates.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts.incoming_request import (
    Channel,
    ChannelCapability,
    CHANNEL_CAPABILITY,
    IncomingRequest,
)
from ..routing.router import RouteDecision, route_request
from ..specialists.contracts import SpecialistStatus
from ..specialists.knowledge_specialist import run_knowledge_specialist
from ..specialists.support_specialist import run_support_specialist
from .context_projection import project_for_knowledge, project_for_support
from .state import SharedRuntimeState
from .trace import TraceCollector

_CUSTOMER_CONTEXT_FIELDS = (
    "plan", "region", "role", "permissions", "contract_status", "account_status",
)


class A1RunResult(BaseModel):
    request_id: str
    channel: Channel
    capability_status: ChannelCapability
    intents: list[str] = Field(default_factory=list)
    risk_signals: dict = Field(default_factory=dict)
    selected_lanes: list[str] = Field(default_factory=list)
    lane_results: dict = Field(default_factory=dict)
    evidence_summary: dict = Field(default_factory=dict)
    grounding_status: dict = Field(default_factory=dict)
    proposed_action: dict | None = None
    authorization_status: str = "NOT_AUTHORIZED"
    trace: list = Field(default_factory=list)


def _normalize(raw_text: str) -> dict:
    from agent.intent_normalizer import normalize_multi

    return normalize_multi(raw_text, allow_llm=False)  # deterministic, no LLM


def _risk(raw_text: str) -> dict:
    from agent.reasoner import compute_l2_signals

    return compute_l2_signals(raw_text)


def _compile_grounding(draft: str, evidence: list[dict]) -> dict:
    from agent.grounding_compiler import compile_grounding

    return compile_grounding(draft, evidence, no_service=True)  # fail-closed deterministic


def _authorize(
    raw_text: str,
    classification: dict,
    kb_results: list,
    history: dict,
    draft: dict,
    tone: dict,
    grounding_check: dict,
    signals: dict,
    customer_context: dict | None,
) -> str:
    from agent.reasoner import synthesize

    result = synthesize(
        raw_text, classification, kb_results, history, draft, tone,
        grounding_check=grounding_check, precomputed_signals=signals,
        customer_context=customer_context, no_service=True,
    )
    return result.get("action", "ESCALATE_L1")


def _context_status(sender_context: dict | None) -> dict | None:
    if not isinstance(sender_context, dict) or not sender_context:
        return None
    present = [k for k in _CUSTOMER_CONTEXT_FIELDS if k in sender_context]
    return {"complete": len(present) == len(_CUSTOMER_CONTEXT_FIELDS), "present": present}


def _merge_lane_results(lane_results: dict, primary_intent: str, all_intents: list[str]) -> dict:
    evidence: list[dict] = []
    seen: set[str] = set()
    for res in lane_results.values():
        for e in res.get("evidence", []):
            doc = e.get("doc_id")
            if doc is None or doc not in seen:
                seen.add(doc)  # type: ignore[arg-type]
                evidence.append(e)
    drafts = [r.get("proposal", {}).get("draft", "") for r in lane_results.values()]
    merged_draft = "\n".join(d for d in drafts if d)
    secondary = all_intents[1] if len(all_intents) > 1 else None
    classification = {
        "intent": primary_intent,
        "confidence": 0.95 if all_intents else 0.4,
        "secondary_intent": secondary,
    }
    return {
        "evidence": evidence,
        "draft": merged_draft,
        "draft_dict": {"reply": merged_draft},
        "classification": classification,
        "history": {"ticket_count": 0},
        "tone": {"tone": "neutral", "churn_risk": 0.0, "urgency": "low", "churn_signals": []},
    }


def _finish(state: SharedRuntimeState, route: RouteDecision, trace: TraceCollector,
            proposal: dict | None, authorization: str) -> A1RunResult:
    doc_ids = sorted({e.get("doc_id", "") for e in state.evidence if e.get("doc_id")})
    return A1RunResult(
        request_id=state.request.request_id,
        channel=state.request.channel,
        capability_status=state.capability_status,
        intents=state.normalized_intents,
        risk_signals=state.risk_signals,
        selected_lanes=route.selected_lanes,
        lane_results=state.lane_results,
        evidence_summary={"count": len(state.evidence), "doc_ids": doc_ids},
        grounding_status=state.grounding_status,
        proposed_action=proposal,
        authorization_status=authorization,
        trace=[e.model_dump() for e in trace.events()],
    )


def run_a1(request: IncomingRequest, *, clock=None) -> A1RunResult:
    trace = TraceCollector(request.request_id, clock=clock)
    trace.emit("request_received", "runtime", stage="ingest",
               payload={"channel": request.channel.value})

    norm = _normalize(request.raw_text)
    intent_set = norm.get("intent_set", ["unknown"])
    trace.emit("intent_normalized", "normalization", payload={"intent_set": intent_set})

    signals = _risk(request.raw_text)
    trace.emit("risk_detected", "router",
               payload={"sla_signal": signals.get("sla_signal"),
                        "hidden_cancel_signal": signals.get("hidden_cancel_signal")})

    ctx_status = _context_status(request.sender_context)
    state = SharedRuntimeState(
        request=request,
        capability_status=CHANNEL_CAPABILITY[request.channel],
        normalized_intents=intent_set,
        risk_signals=signals,
        context_status=ctx_status,
    )

    route = route_request(
        channel=request.channel, intent_set=intent_set, risk_signals=signals,
        context_status=ctx_status, raw_text=request.raw_text,
    )
    trace.emit("route_decided", "router", reason_codes=route.reason_codes,
               payload={"selected_lanes": route.selected_lanes,
                        "capability_status": route.capability_status,
                        "early_stop": route.early_stop})
    state.route_decision = route.model_dump()

    if route.early_stop:
        trace.emit("route_early_stop", "router",
                   reason_codes=[route.early_stop_reason or ""],
                   payload={"reason": route.early_stop_reason})
        if route.early_stop_reason == "channel_routing_only":
            # No ticket specialist, no authorization decision, no side effect.
            return _finish(state, route, trace, proposal=None, authorization="NOT_AUTHORIZED")
        # early-risk pre-guard: skip drafting / tool loop; authorize via existing gate.
        merged = {
            "evidence": [], "draft": "", "draft_dict": {},
            "classification": {"intent": intent_set[0] if intent_set else "unknown",
                               "confidence": 0.4,
                               "secondary_intent": intent_set[1] if len(intent_set) > 1 else None},
            "history": {"ticket_count": 0},
            "tone": {"tone": "neutral", "churn_risk": 0.0, "urgency": "low", "churn_signals": []},
        }
        action = _authorize(request.raw_text, merged["classification"], [], merged["history"],
                            {}, merged["tone"], {}, signals, request.sender_context)
        trace.emit("authorization_decided", "authorization", payload={"action": action})
        state.authorization = {"action": action}
        return _finish(state, route, trace, proposal=None, authorization=action)

    # ── run selected specialist lanes per intent slice ──────────────────────
    lane_results: dict = {}
    all_evidence: list[dict] = []
    for slice_ in route.intent_slices:
        intent = slice_.get("intent", "unknown")

        kinput = project_for_knowledge(state, slice_)
        trace.emit("context_projected", "projection", stage="knowledge",
                   payload={"intent": intent})
        trace.emit("lane_started", "knowledge", payload={"intent": intent})
        kres = run_knowledge_specialist(kinput)
        trace.emit("tool_called", "knowledge",
                   payload={"tool": "search_knowledge_base", "intent": intent,
                            "status": kres.status.value,
                            "evidence_count": len(kres.evidence)})
        trace.emit("lane_completed", "knowledge",
                   payload={"intent": intent, "coverage": kres.coverage,
                            "status": kres.status.value})

        sinput = project_for_support(state, slice_, kres.evidence)
        trace.emit("context_projected", "projection", stage="support",
                   payload={"intent": intent})
        trace.emit("lane_started", "support", payload={"intent": intent})
        sres = run_support_specialist(sinput)
        trace.emit("lane_completed", "support",
                   payload={"intent": intent, "status": sres.status.value,
                            "evidence_refs": sres.evidence_refs})

        lane_results[intent] = {
            "evidence": kres.evidence,
            "proposal": sres.proposal,
            "knowledge_status": kres.status.value,
            "support_status": sres.status.value,
        }
        all_evidence.extend(kres.evidence)

    state.lane_results = lane_results
    state.evidence = all_evidence

    # ── merge (deterministic) + grounding (legacy, fail-closed) + authorize ──
    primary = intent_set[0] if intent_set else "unknown"
    merged = _merge_lane_results(lane_results, primary, intent_set)
    grounding_check = _compile_grounding(merged["draft"], merged["evidence"])
    trace.emit("grounding_checked", "grounding",
               reason_codes=[grounding_check.get("reason_code") or "ok"],
               payload={"grounding_ratio": grounding_check.get("grounding_ratio"),
                        "auto_reply_safe": grounding_check.get("auto_reply_safe")})
    state.grounding_status = grounding_check

    action = _authorize(request.raw_text, merged["classification"], merged["evidence"],
                        merged["history"], merged["draft_dict"], merged["tone"],
                        grounding_check, signals, request.sender_context)
    trace.emit("authorization_decided", "authorization", payload={"action": action})
    state.authorization = {"action": action}

    proposal = {"draft": merged["draft"], "grounded": bool(grounding_check.get("auto_reply_safe"))}
    trace.emit("final_proposal", "proposal",
               payload={"action": action, "grounded": proposal["grounded"]})

    return _finish(state, route, trace, proposal=proposal, authorization=action)
