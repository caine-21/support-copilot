"""
Context-aware entitlement guard (v2).

Architecture:
  LLM extract_user_context()  → structured {plan, region}   (understands paraphrase)
  rule-based constraint check → SAFE / BLOCKED               (deterministic policy)

Separation of concerns:
  LLM layer  — "who is this user and what context do they bring"
  Rule layer — "given that context, is AUTO_REPLY safe"

v1 used keyword matching (_TEAM_SIGNALS list). Brittle: missed paraphrases
("large org", "corporate tier", "our company"), and rules inflated toward
keyword engineering. v2 delegates context extraction to LLM; rules stay clean.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from llm import call_llm, safe_json_parse

# ── Entitlement annotations (deterministic, human-maintained) ─────────────────
# These do not change with model updates — only change when FAQ policy changes.

_ENTERPRISE_ONLY = {
    "FAQ-security-01": "SSO (SAML/OIDC)",
    "FAQ-security-03": "Audit logs",
    "FAQ-billing-04":  "Custom invoice (cost center / PO number)",
}

_PLAN_DEPENDENT = {
    "FAQ-feature-07": "Version history retention (90d Team / indefinite Enterprise)",
    "FAQ-feature-08": "API rate limits (100/min Team / 1000/min Enterprise)",
    "FAQ-security-02": "EU data residency (Enterprise contract only)",
    "FAQ-troubleshoot-03": "Trash recovery after Trash empty (Enterprise CSM only)",
}

# ── LLM-based structured extraction ──────────────────────────────────────────

_EXTRACT_SYSTEM = """\
Extract user context from the support ticket. Output JSON only.

{
  "plan": "team" | "enterprise" | "unknown",
  "region": "EU" | "US" | "APAC" | "unknown",
  "plan_evidence": "<quoted phrase from ticket that reveals plan, or empty string>"
}

plan detection rules:
  "enterprise" → user mentions enterprise plan, large org, corporate, company-wide, 200+ users, CSM, dedicated account
  "team" → user mentions team plan, small team, startup, personal plan, free plan, <50 users
  "unknown" → no plan context in ticket"""


def extract_user_context(ticket_text: str) -> dict:
    """
    Use LLM to extract structured user context.
    Returns: {plan: str, region: str, plan_evidence: str}
    Fallback to {plan: "unknown", region: "unknown"} on any error.
    """
    try:
        raw = call_llm(_EXTRACT_SYSTEM, f"Ticket: {ticket_text}")
        parsed = safe_json_parse(raw)
        return {
            "plan":           parsed.get("plan", "unknown"),
            "region":         parsed.get("region", "unknown"),
            "plan_evidence":  parsed.get("plan_evidence", ""),
        }
    except Exception as e:
        print(f"[ContextGuard] extract failed ({e}), defaulting to unknown")
        return {"plan": "unknown", "region": "unknown", "plan_evidence": ""}


# ── Constraint check (deterministic) ─────────────────────────────────────────

def check(ticket_text: str, kb_results: list) -> dict:
    """
    Two-phase check:
      1. Extract structured user context via LLM
      2. Apply deterministic entitlement rules

    Returns:
      {
        "safe": bool,
        "flag": "plan_mismatch" | "plan_unknown" | None,
        "reason": str,
        "user_context": {plan, region, plan_evidence},
      }
    """
    user_ctx = extract_user_context(ticket_text)
    plan     = user_ctx["plan"]
    kb_ids   = {r["doc_id"] for r in kb_results}

    # Rule 1: team-plan user asking about enterprise-only feature
    if plan == "team":
        for doc_id, feature in _ENTERPRISE_ONLY.items():
            if doc_id in kb_ids:
                return {
                    "safe": False,
                    "flag": "plan_mismatch",
                    "reason": f"User is on Team plan (evidence: '{user_ctx['plan_evidence']}') but '{feature}' requires Enterprise (KB: {doc_id})",
                    "user_context": user_ctx,
                }

    # Rule 2: plan-dependent feature, plan unknown — can't safely auto-reply
    if plan == "unknown":
        for doc_id, feature in _PLAN_DEPENDENT.items():
            if doc_id in kb_ids:
                return {
                    "safe": False,
                    "flag": "plan_unknown",
                    "reason": f"Answer varies by plan tier ({feature}) but plan not identifiable from ticket (KB: {doc_id})",
                    "user_context": user_ctx,
                }

    # Rule 3: EU region + non-enterprise → can't guarantee EU residency
    if user_ctx["region"] == "EU" and plan != "enterprise":
        if "FAQ-security-02" in kb_ids:
            return {
                "safe": False,
                "flag": "region_plan_conflict",
                "reason": f"EU region detected but EU data residency is Enterprise contract-only (plan={plan})",
                "user_context": user_ctx,
            }

    return {
        "safe": True,
        "flag": None,
        "reason": f"no entitlement conflict (plan={plan}, region={user_ctx['region']})",
        "user_context": user_ctx,
    }
