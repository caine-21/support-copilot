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
from churn_policy import resolve_churn

_GROUNDING_STRONG = 0.60  # direct answer in KB — safe to auto-reply
_GROUNDING_WEAK   = 0.40  # related content found — inform L1 agent, don't auto-reply

# classify_intent LLM outputs treated as technical (supplement INL technical set)
_LM_TECHNICAL_LABELS: frozenset[str] = frozenset({"bug", "error", "technical", "sync_failure"})

_SLA_KEYWORDS: tuple[str, ...] = ("breach", "downtime", "data loss")

_HIDDEN_CANCEL_KEYWORDS: tuple[str, ...] = (
    "justify the renewal", "renewal cost", "decide to move on",
    "considering moving on", "evaluating whether", "transfer account ownership",
    "switching to a competitor", "moving to a competitor",
    "evaluating switching to", "switch to a competitor",
    "formally file a complaint", "file a formal complaint",
    "formal complaint against", "data exposure",
    "on social media", "senior manager",
    "speak to a manager", "speak with a manager", "escalate to management",
)


def compute_l2_signals(ticket_text: str) -> dict:
    """Deterministic L2 routing signals — pure regex/keyword, zero LLM cost.

    Extracted so agent_loop can short-circuit before draft_reply.
    """
    sla = (
        bool(re.search(r'\bsla\b', ticket_text, re.IGNORECASE))
        or any(kw in ticket_text.lower() for kw in _SLA_KEYWORDS)
    )
    cancel = any(kw in ticket_text.lower() for kw in _HIDDEN_CANCEL_KEYWORDS)
    return {"sla_signal": sla, "hidden_cancel_signal": cancel}


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


# ── assumption trace (Fact-Grounded Reasoning Protocol v0) ────────────────────
# Read-only shadow layer over an already-computed decision. Does NOT touch any
# routing branch. Separates VERIFIED facts (deterministic regex/keyword hits on
# real ticket text) from ASSUMED drivers (LLM inferences: churn_risk, tone,
# intent confidence). An assumed value sitting within _BOUNDARY_MARGIN of the
# threshold that gates the action is flagged high-risk — this is exactly the
# probabilistic intent-ambiguity class (T-018/T-052: churn signal at boundary).
_CHURN_THRESHOLD = 0.80   # churn_risk LLM-fallback escalation bar (Rule 1)
_CONF_THRESHOLD  = 0.65   # intent confidence deduction bar
_BOUNDARY_MARGIN = 0.07   # |value - threshold| <= margin → boundary assumption

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
    contested: bool,
) -> dict:
    """Auditable separation of verified facts vs latent assumptions behind `action`."""
    drivers = [
        {"signal": "sla_signal", "value": sla_signal,
         "source": "deterministic", "status": "verified", "risk": "low"},
        {"signal": "hidden_cancel_signal", "value": hidden_cancel_signal,
         "source": "deterministic", "status": "verified", "risk": "low"},
        {"signal": "grounding", "value": grounding,
         "source": "deterministic", "status": "verified", "risk": "low"},
    ]

    churn_boundary = abs(churn_risk - _CHURN_THRESHOLD) <= _BOUNDARY_MARGIN
    conf_boundary  = abs(intent_conf - _CONF_THRESHOLD) <= _BOUNDARY_MARGIN
    drivers += [
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

    # load-bearing = assumed drivers whose flip could change the action
    load_bearing = [d["signal"] for d in drivers
                    if d["status"] == "assumed" and d["risk"] == "high"]
    if contested:
        load_bearing.append("churn_reading_contested")

    max_risk = max((d["risk"] for d in drivers),
                   key=lambda r: _RISK_ORDER[r], default="low")

    return {
        "decision": action,
        "drivers": drivers,
        "load_bearing_assumptions": load_bearing,
        "max_assumption_risk": max_risk,
    }


def synthesize(
    ticket_text: str,
    classification: dict,
    kb_results: list,
    history: dict,
    draft: dict,
    tone: dict,
    grounding_check: dict | None = None,
    precomputed_signals: dict | None = None,
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

    # L2 signals — computed once, reused for priority and action blocks.
    _sigs = precomputed_signals or compute_l2_signals(ticket_text)
    sla_signal           = _sigs["sla_signal"]
    hidden_cancel_signal = _sigs["hidden_cancel_signal"]

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
    # SLA/cancel always P1 even when tone_check was skipped (early-exit path).
    if sla_signal or hidden_cancel_signal:
        priority = "P1"
    elif tone_label == "frustrated" or churn_risk >= 0.6 or urgency == "high":
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

    # ── churn policy: explicit reading over the implicit churn_risk>=0.8 monopoly ──
    # Each churn_signal is read EXIT_THREAT vs TRANSACTION. A high churn_risk whose
    # signals are ALL transaction/eligibility (e.g. a refund request) is NOT churn —
    # demote to L1: a human handles the transaction, but never auto-reply a refund.
    _churn = resolve_churn(tone.get("churn_signals", []), ticket_text)
    churn_demoted_to_l1 = False
    if churn_escalate and _churn["non_product_churn"]:
        churn_escalate = False
        churn_demoted_to_l1 = True

    if churn_escalate or sla_signal or hidden_cancel_signal:
        action = "ESCALATE_L2"
        reason = (f"churn_risk={churn_risk:.2f}, tone={tone_label}, "
                  f"sla={sla_signal}, hidden_cancel={hidden_cancel_signal}")

    # Rule 1b: churn reading demoted (high churn_risk but transaction-only) → L1, never auto-reply
    elif churn_demoted_to_l1:
        action = "ESCALATE_L1"
        reason = (f"churn_risk={churn_risk:.2f} but signals are non-product-churn "
                  f"(transaction or communication preference) — L1 for human review, not auto-reply")
        missing_info.append("churn reading: non-product-churn (refund/newsletter != product churn)")

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

    # Contested churn (exit AND transaction readings present): collapse stands, but it
    # must not be autonomous — block AUTO_REPLY under unresolved disagreement (teeth).
    if action == "AUTO_REPLY" and _churn["contested"]:
        action = "ESCALATE_L1"
        reason = "churn reading contested (exit vs transaction) — blocked autonomous reply"
        missing_info.append("contested churn reading")

    # routing_signals: observable facts that drove the decision (Milestone C log format)
    routing_signals = (
        (["sla_signal"] if sla_signal else [])
        + (["competitor_exit"] if hidden_cancel_signal else [])
        + (["churn_risk_high"] if churn_escalate else [])
        + (["churn_demoted_communication_preference"]
           if churn_demoted_to_l1 and _churn["communication_preference"] else [])
        + (["churn_demoted_transaction"]
           if churn_demoted_to_l1 and _churn["all_transaction"] else [])
        + (["churn_contested"] if _churn["contested"] else [])
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
        "churn_readings": _churn["readings"],
        "churn_contested": _churn["contested"],
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
        "assumption_trace": assumption_trace(   # Fact-Grounded Reasoning Protocol v0
            action,
            intent_conf=intent_conf,
            churn_risk=churn_risk,
            tone_label=tone_label,
            grounding=grounding,
            sla_signal=sla_signal,
            hidden_cancel_signal=hidden_cancel_signal,
            contested=_churn["contested"],
        ),
    }


# ── assumption replay (policy-sensitivity probe over a decision) ──────────────
# Re-invokes synthesize() as a black box with one (or all) LLM assumption(s)
# neutralized to a non-triggering baseline, and diffs the resulting `action`.
# Zero LLM cost (synthesize does no LLM calls), zero side effects, routing logic
# untouched. NOTE: "neutralize" = set the assumption to the value at which it no
# longer pushes the decision (a modeling choice, not ground truth).
#
# WHAT THIS MEASURES — read carefully: this probes POLICY SENSITIVITY, not WORLD
# CAUSALITY. We perturb the model's *belief inputs* and re-run the *same policy*;
# it answers "if the model didn't believe this assumption, would the decision
# change" — NOT "if the underlying fact were different, what would happen". One
# level apart, easy to conflate.
#
#   single-driver flip  → decision is load-bearing on that assumption (policy-sensitive)
#   all-neutral == base → decision is FACT-STABILIZED (verified facts decide it)
#   all-neutral != base → decision is ASSUMPTION-DEPENDENT (only holds via inference)
#
# Limitation: single-driver probes miss interaction effects (two assumptions each
# inert alone but load-bearing jointly). The all-neutral probe catches the joint
# case; full subset attribution (Shapley) is intentionally out of scope for v0.

# neutralizing value per assumed driver — the non-escalating / no-deduction baseline
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
    precomputed_signals: dict | None = None,
) -> dict:
    """Counterfactual: which LLM assumptions actually drive this decision?"""
    _ASSUMED = ("churn_risk", "intent_confidence", "tone")

    def _action(c: dict, t: dict) -> str:
        return synthesize(ticket_text, c, kb_results, history, draft, t,
                          grounding_check, precomputed_signals)["action"]

    baseline = _action(classification, tone)

    per_driver = {}
    load_bearing = []
    for d in _ASSUMED:
        c, t = _neutralize(classification, tone, d)
        after = _action(c, t)
        flips = after != baseline
        per_driver[d] = {"action_if_removed": after, "load_bearing": flips}
        if flips:
            load_bearing.append(d)

    # all assumptions neutralized at once → fact-grounded vs assumption-driven
    # (_neutralize deep-copies internally, so chaining is safe and non-mutating)
    c_all, t_all = classification, tone
    for d in _ASSUMED:
        c_all, t_all = _neutralize(c_all, t_all, d)
    all_neutral_action = _action(c_all, t_all)

    return {
        "baseline_action": baseline,
        "per_assumption": per_driver,
        "load_bearing_assumptions": load_bearing,
        "all_assumptions_neutralized_action": all_neutral_action,
        "verdict": ("fact_grounded" if all_neutral_action == baseline
                    else "assumption_driven"),
    }
