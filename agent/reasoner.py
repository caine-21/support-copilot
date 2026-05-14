"""
Reasoner: synthesize tool observations → final verdict with action.
Includes context_guard v1: blocks AUTO_REPLY when plan-tier context conflicts with KB entry.


Action tiers:
  AUTO_REPLY    — high confidence + KB-grounded + no churn signal
  ESCALATE_L1   — ambiguous / missing info / moderate concern
  ESCALATE_L2   — frustrated + churn signal / SLA dispute

Grounding is deterministic: KB score threshold, NOT LLM self-assessment.
"""

import context_guard as _guard

_GROUNDING_STRONG = 0.60  # direct answer in KB — safe to auto-reply
_GROUNDING_WEAK   = 0.40  # related content found — inform L1 agent, don't auto-reply


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

    # ── action decision (3 rules) ─────────────────────────────────────────────

    # Rule 1: churn / SLA signal → L2
    churn_escalate = churn_risk >= 0.6 or (tone_label == "frustrated" and churn_risk >= 0.4)
    sla_signal = any(kw in ticket_text.lower() for kw in ["sla", "breach", "downtime", "data loss"])

    if churn_escalate or sla_signal:
        action = "ESCALATE_L2"
        reason = f"churn_risk={churn_risk:.2f}, tone={tone_label}, sla_signal={sla_signal}"

    # Rule 2: AUTO_REPLY safety gate — strong grounding + context guard required
    # context_guard v1: blocks AUTO_REPLY when plan-tier context conflicts with KB entry
    elif confidence >= 0.75 and grounding == "strong":
        guard = _guard.check(ticket_text, kb_grounding)
        if not guard["safe"]:
            action = "ESCALATE_L1"
            reason = f"context_guard blocked AUTO_REPLY — {guard['reason']}"
            missing_info.append(f"entitlement conflict: {guard['reason']}")
        else:
            action = "AUTO_REPLY"
            reason = f"confidence={confidence}, KB strong-grounded (top_score >= {_GROUNDING_STRONG})"

    # Rule 3: weak grounding or low confidence → L1 (safe fallback)
    else:
        action = "ESCALATE_L1"
        reason = f"confidence={confidence}, grounding={grounding} — L1 with KB reference attached"

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
        "missing_info": missing_info,
    }
