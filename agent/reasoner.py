"""
Reasoner: synthesize tool observations → final verdict with action.
Includes context_guard v1: blocks AUTO_REPLY when plan-tier context conflicts with KB entry.


Action tiers:
  AUTO_REPLY    — high confidence + KB-grounded + no churn signal
  ESCALATE_L1   — ambiguous / missing info / moderate concern
  ESCALATE_L2   — frustrated + churn signal / SLA dispute

Grounding is deterministic: KB score threshold, NOT LLM self-assessment.
"""

import re
import copy
import context_guard as _guard
from intent_normalizer import normalize_multi, TECHNICAL_INTENTS, BILLING_INTENTS, CANCEL_INTENTS

_GROUNDING_STRONG = 0.60  # direct answer in KB — safe to auto-reply
_GROUNDING_WEAK   = 0.40  # related content found — inform L1 agent, don't auto-reply

# classify_intent LLM outputs treated as technical (supplement INL technical set)
_LM_TECHNICAL_LABELS: frozenset[str] = frozenset({"bug", "error", "technical", "sync_failure"})

# -- assumption trace (read-only observability) -------------------------------
# These fields describe which already-computed signals the policy relied on.
# They do not feed back into routing, grounding, or safety decisions.
_CHURN_THRESHOLD = 0.80
_CONF_THRESHOLD = 0.65
_BOUNDARY_MARGIN = 0.07
_RISK_ORDER = {"low": 0, "med": 1, "high": 2}


def assumption_trace(
    action: str,
    *,
    intent_conf: float,
    churn_risk: float,
    tone_label: str,
    grounding: str,
    sla_signal: bool,
    hidden_cancel_signal: bool,
) -> dict:
    """Return an audit trace for a completed decision without changing it."""
    churn_boundary = abs(churn_risk - _CHURN_THRESHOLD) <= _BOUNDARY_MARGIN
    conf_boundary = abs(intent_conf - _CONF_THRESHOLD) <= _BOUNDARY_MARGIN

    drivers = [
        {"signal": "sla_signal", "value": sla_signal,
         "source": "deterministic", "status": "verified", "risk": "low"},
        {"signal": "hidden_cancel_signal", "value": hidden_cancel_signal,
         "source": "deterministic", "status": "verified", "risk": "low"},
        {"signal": "grounding", "value": grounding,
         "source": "deterministic", "status": "verified", "risk": "low"},
        {"signal": "churn_risk", "value": round(churn_risk, 2),
         "source": "llm_inferred", "status": "assumed",
         "risk": "high" if churn_boundary else "med",
         "note": "within boundary of escalation threshold" if churn_boundary else ""},
        {"signal": "intent_confidence", "value": round(intent_conf, 2),
         "source": "llm_inferred", "status": "assumed",
         "risk": "high" if conf_boundary else "med",
         "note": "within boundary of deduction threshold" if conf_boundary else ""},
        {"signal": "tone", "value": tone_label,
         "source": "llm_inferred", "status": "assumed", "risk": "med", "note": ""},
    ]
    load_bearing = [
        d["signal"] for d in drivers
        if d["status"] == "assumed" and d["risk"] == "high"
    ]
    max_risk = max((d["risk"] for d in drivers), key=lambda r: _RISK_ORDER[r], default="low")
    return {
        "decision": action,
        "drivers": drivers,
        "load_bearing_assumptions": load_bearing,
        "max_assumption_risk": max_risk,
    }


def grounding_level(kb_results: list) -> str:
    """
    3-level deterministic grounding based on top KB score.
    'strong' → AUTO_REPLY safe
    'weak'   → KB helps but auto-reply risky (partial match, not authoritative)
    'none'   → no KB coverage — must escalate
    """
    if not kb_results:
        return "none"
    top_score = max(r.get("score", 0) for r in kb_results)
    if top_score >= _GROUNDING_STRONG:
        return "strong"
    if top_score >= _GROUNDING_WEAK:
        return "weak"
    return "none"


def synthesize(
    ticket_text: str,
    classification: dict,
    kb_results: list,
    history: dict,
    draft: dict,
    tone: dict,
    grounding_check: dict | None = None,
) -> dict:
    intent = classification.get("intent", "other")
    intent_conf = classification.get("confidence", 0.5)
    secondary = classification.get("secondary_intent")
    kb_grounding = kb_results if kb_results else []
    grounding = grounding_level(kb_grounding)   # "strong" | "weak" | "none"
    tone_label = tone.get("tone", "neutral")
    churn_risk = tone.get("churn_risk", 0.0)
    urgency = tone.get("urgency", "medium")
    past_count = history.get("ticket_count", 0)

    missing_info: list[str] = []
    deductions: list[str] = []
    confidence = 0.85

    # ── confidence scoring ────────────────────────────────────────────────────

    if intent_conf < 0.65:
        confidence -= 0.20
        deductions.append(f"−0.20: intent confidence low ({intent_conf:.2f})")
        missing_info.append("intent ambiguous")

    if grounding == "none":
        confidence -= 0.25
        deductions.append("−0.25: no KB grounding")
        missing_info.append("no FAQ match — cannot ground reply")
    elif grounding == "weak":
        confidence -= 0.10
        deductions.append("−0.10: KB weak match (partial coverage)")

    if secondary:
        confidence -= 0.10
        deductions.append("−0.10: multi-intent ticket")
        missing_info.append(f"secondary intent: {secondary}")

    if past_count >= 2:
        deductions.append(f"note: {past_count} prior tickets from this user")

    confidence_why = f"base=0.85; {', '.join(deductions)}" if deductions else "base=0.85; all signals clean"
    confidence = round(max(0.0, min(1.0, confidence)), 2)

    # ── priority ─────────────────────────────────────────────────────────────

    if tone_label == "frustrated" or churn_risk >= 0.6 or urgency == "high":
        priority = "P1"
    elif intent in ("bug",) or urgency == "medium":
        priority = "P2"
    else:
        priority = "P3"

    # ── intent-class gate (Milestone B) ──────────────────────────────────────
    # normalize_multi() is pure CPU — no LLM call, negligible cost.
    _multi = normalize_multi(ticket_text)
    _intent_set = set(_multi.get("intent_set", ["unknown"]))

    # LLM classify_intent label also contributes to technical detection
    _lm_technical = intent in _LM_TECHNICAL_LABELS
    has_technical = _lm_technical or bool(_intent_set & TECHNICAL_INTENTS)
    has_billing   = bool(_intent_set & BILLING_INTENTS)
    has_cancel    = bool(_intent_set & CANCEL_INTENTS)

    # ── action decision (3 rules) ─────────────────────────────────────────────

    # Rule 1: deterministic signals + LLM fallback → L2
    #
    # Architecture (Milestone B→C transition):
    #   Primary:  sla_signal + hidden_cancel_signal (deterministic text patterns)
    #   Fallback: churn_risk >= 0.8 (LLM, very high bar — catches "I'm done with
    #             this company" when no explicit keyword fires)
    #
    # NOT used: frustrated tone, 0.4/0.6 thresholds — these were per-LLM-run noise.
    # intent-class flags (has_technical, has_billing, has_cancel) are logged below
    # and reserved for Milestone C deterministic signal expansion.

    # \bsla\b: word-boundary match to avoid "Slack" → "sla" false positive.
    sla_signal = (
        bool(re.search(r'\bsla\b', ticket_text, re.IGNORECASE))
        or any(kw in ticket_text.lower() for kw in ["breach", "downtime", "data loss"])
    )
    # Explicit exit/competitor/escalation signals — deterministic, auditable.
    hidden_cancel_signal = any(kw in ticket_text.lower() for kw in [
        "justify the renewal",
        "renewal cost",
        "decide to move on",
        "considering moving on",
        "evaluating whether",
        "transfer account ownership",
        "switching to a competitor",
        "moving to a competitor",
        "evaluating switching to",
        "switch to a competitor",
        # Formal escalation: always L2 (complaint filing = contractual/legal risk)
        "formally file a complaint",
        "file a formal complaint",
        "formal complaint against",
        "data exposure",
        # Reputation threat + senior escalation demand (T-082 gap)
        # Social media threats and management-bypass demands → always L2 (PR/legal risk)
        # "on social media" (not bare "social media") avoids "social media campaigns" false match
        "on social media",
        "senior manager",
        "speak to a manager",
        "speak with a manager",
        "escalate to management",
    ])
    # Billing dispute + cancel language: investigate billing first → L1.
    # Competitor-exit and SLA signals still override via hidden_cancel/sla_signal.
    # LLM score suppressed: "invoice wrong + cancel" can legitimately score 0.8+
    # churn_risk because the LLM sees "cancel" — but this is a billing dispute, not exit.
    if has_billing and has_cancel:
        churn_escalate = False
    else:
        # LLM fallback: 0.8 avoids frustrated-but-not-churning technical tickets.
        # Catches unambiguous "I'm leaving" intent when no keyword fires.
        churn_escalate = churn_risk >= 0.8

    if churn_escalate or sla_signal or hidden_cancel_signal:
        action = "ESCALATE_L2"
        reason = (f"churn_risk={churn_risk:.2f}, tone={tone_label}, "
                  f"sla={sla_signal}, hidden_cancel={hidden_cancel_signal}")

    # Rule 2: AUTO_REPLY safety gate — strong grounding + context guard + KB closure required
    # context_guard v1: blocks AUTO_REPLY when plan-tier context conflicts with KB entry
    # grounding_compiler (Milestone D): blocks AUTO_REPLY when draft exceeds KB boundary
    elif confidence >= 0.75 and grounding == "strong":
        guard = _guard.check(ticket_text, kb_grounding)
        gc = grounding_check or {}
        gc_safe   = gc.get("auto_reply_safe", True)   # default True when compiler skipped
        gc_ratio  = gc.get("grounding_ratio", 1.0)
        gc_ungnd  = gc.get("ungrounded_claims", [])

        if not guard["safe"]:
            action = "ESCALATE_L1"
            reason = f"context_guard blocked AUTO_REPLY — {guard['reason']}"
            missing_info.append(f"entitlement conflict: {guard['reason']}")
        elif not gc_safe:
            action = "ESCALATE_L1"
            reason = (f"grounding_compiler: ratio={gc_ratio:.2f} < required — "
                      f"draft contains claims beyond KB boundary")
            missing_info.append(f"ungrounded claims: {gc_ungnd[:2]}")
        else:
            action = "AUTO_REPLY"
            reason = f"confidence={confidence}, KB strong-grounded (top_score >= {_GROUNDING_STRONG})"

    # Rule 3: weak grounding or low confidence → L1 (safe fallback)
    else:
        action = "ESCALATE_L1"
        reason = f"confidence={confidence}, grounding={grounding} — L1 with KB reference attached"

    # routing_signals: observable facts that drove the decision (Milestone C log format)
    routing_signals = (
        (["sla_signal"] if sla_signal else [])
        + (["competitor_exit"] if hidden_cancel_signal else [])
        + (["churn_risk_high"] if churn_escalate else [])
    )

    return {
        "ticket_id": None,
        "grounding": grounding,
        "intent": intent,
        "secondary_intent": secondary,
        "priority": priority,
        "tone": tone_label,
        "churn_risk": churn_risk,
        "churn_signals": tone.get("churn_signals", []),
        "kb_grounding": [{"doc_id": r["doc_id"], "snippet": r["snippet"][:150]} for r in kb_grounding],
        "draft_reply": draft.get("reply", ""),
        "confidence": confidence,
        "confidence_why": confidence_why,
        "action": action,
        "reason": reason,
        "routing_signals": routing_signals,
        "intent_class": {
            "has_technical": has_technical,
            "has_billing":   has_billing,
            "has_cancel":    has_cancel,
        },
        "missing_info": missing_info,
        "intent_set": sorted(_intent_set),  # for RAGAS retrieval recall
        "grounding_check": {                # Milestone D: claim graph
            "grounding_ratio":   (grounding_check or {}).get("grounding_ratio", 1.0),
            "auto_reply_safe":   (grounding_check or {}).get("auto_reply_safe", True),
            "ungrounded_claims": (grounding_check or {}).get("ungrounded_claims", []),
        },
        "assumption_trace": assumption_trace(
            action,
            intent_conf=intent_conf,
            churn_risk=churn_risk,
            tone_label=tone_label,
            grounding=grounding,
            sla_signal=sla_signal,
            hidden_cancel_signal=hidden_cancel_signal,
        ),
    }


# -- offline assumption replay ------------------------------------------------
# This utility intentionally is NOT called from run_agent. It re-runs synthesize()
# with selected LLM-derived assumptions neutralized, so it is useful for offline
# analysis but should not add cost or policy coupling to the main request path.
def _neutralize(classification: dict, tone: dict, driver: str) -> tuple[dict, dict]:
    c, t = copy.deepcopy(classification), copy.deepcopy(tone)
    if driver == "churn_risk":
        t["churn_risk"] = 0.0
        t["churn_signals"] = []
    elif driver == "intent_confidence":
        c["confidence"] = 1.0
    elif driver == "tone":
        t["tone"] = "neutral"
    return c, t


def replay_assumptions(
    ticket_text: str,
    classification: dict,
    kb_results: list,
    history: dict,
    draft: dict,
    tone: dict,
    grounding_check: dict | None = None,
) -> dict:
    """Offline policy-sensitivity probe; no LLM calls, no side effects."""
    assumed = ("churn_risk", "intent_confidence", "tone")

    def _action(c: dict, t: dict) -> str:
        return synthesize(ticket_text, c, kb_results, history, draft, t, grounding_check)["action"]

    baseline = _action(classification, tone)
    per_driver = {}
    load_bearing = []
    for driver in assumed:
        c, t = _neutralize(classification, tone, driver)
        after = _action(c, t)
        flips = after != baseline
        per_driver[driver] = {"action_if_removed": after, "load_bearing": flips}
        if flips:
            load_bearing.append(driver)

    c_all, t_all = classification, tone
    for driver in assumed:
        c_all, t_all = _neutralize(c_all, t_all, driver)
    all_neutral_action = _action(c_all, t_all)

    return {
        "baseline_action": baseline,
        "per_assumption": per_driver,
        "load_bearing_assumptions": load_bearing,
        "all_assumptions_neutralized_action": all_neutral_action,
        "verdict": "fact_grounded" if all_neutral_action == baseline else "assumption_driven",
        "mode": "offline_only",
    }
