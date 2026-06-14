"""
Intent Normalization Layer (INL) — v8

Compiles raw user query into structured system ontology before KB retrieval.

v6: text → canonical_text → embedding (probabilistic)
v7: text → intent_id (enum) → FAQ lookup (deterministic)
v8: text → intent_set (list) → parallel FAQ lookup (multi-intent aware)

Embedding is fallback-only when intent_set == ["unknown"].

Design rationale:
- embedding has no "I don't know" — INL adds entity validation and
  deterministic routing for all known intent types.
- LLM role: parser (normalization), not decision maker (routing).
- intent_id is a stable enum key; canonical_query is human-readable label only.
- v8 change: normalize_multi() collects ALL matching intents per ticket.
  Intra-category conflicts resolved by _EXCLUSIVE_GROUPS (first-match-wins within group).
  Cross-category co-occurrence preserved (e.g. cancel + invoice both returned).
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from typing import TypedDict

# ── Product catalog ────────────────────────────────────────────────────────────

_VALID_PLANS = {"personal", "team", "enterprise"}

_UNKNOWN_PLAN_SIGNALS = {
    "platinum", "gold", "silver", "pro", "basic", "starter",
    "premium", "professional", "business", "advanced", "plus",
}

# ── Intent ID enum ─────────────────────────────────────────────────────────────
# Stable keys — matched by INTENT_FAQ_MAP in kb.py.

INTENT_IDS = {
    "payment_methods",
    "cancellation_fee",
    "refund_eligibility",
    "refund_status",      # status inquiry → L1 (needs lookup)
    "invoice_customize",  # customization → L1 (not self-serve)
    "plan_change",
    "cancel_subscription",
    "password_reset",
    "data_export",
    "permission_levels",  # FAQ-feature-02
    "feature_feedback",   # no FAQ → L1
    "version_history",    # FAQ-feature-07
    "sso_issue",          # SSO broken/not working → L1 (no FAQ — needs investigation)
    "sso_setup",          # FAQ-security-01
    "audit_logs",         # FAQ-security-03
    "signup_issue",       # FAQ-troubleshoot-01
    "workspace_setup",    # no FAQ → L1
    "upload_error",       # no FAQ → L1
    "ui_preferences",     # no FAQ → L1
    "account_deletion",
    "sla_uptime",
    "invoice_download",
    "unknown_plan",   # requires_clarification=True
    "unknown",        # LLM fallback — use embedding
}

# ── Rule table ─────────────────────────────────────────────────────────────────
# (trigger_keywords, intent_id, canonical_label, requires_entity_check)
# Order: more specific patterns first to prevent early match by broader keywords.

_RULES: list[tuple[list[str], str, str, bool]] = [
    # Cancellation fee — BEFORE cancel_subscription (shares "cancel" keyword)
    (["cancellation fee", "early termination fee", "termination fee",
      "cancel fee", "fee to cancel", "penalty for cancelling",
      "early termination"],
     "cancellation_fee", "cancellation fee / early termination policy", False),

    # Refund status — BEFORE refund_eligibility (status check ≠ policy question → L1)
    (["status of my refund", "status of the refund", "check my refund",
      "check the refund", "expecting a refund", "expecting my refund",
      "waiting for a refund", "waiting for my refund", "waiting for the refund",
      "refund to be processed", "refund has been processed",
      "where is my refund", "when will my refund", "track my refund"],
     "refund_status", "refund status inquiry", False),

    # Refund — BEFORE cancel_subscription (refund queries often contain "cancel")
    # "reimburse" removed: substring-matches "reimbursement" (T-001 latent bug).
    # Use verb phrases only: "reimburse me", "will reimburse", "get reimbursed".
    (["refund", "money back", "reimburse me", "will reimburse", "get reimbursed",
      "get my money", "charge back"],
     "refund_eligibility", "refund eligibility and policy", False),

    # Payment methods
    (["payment method", "payment option", "accepted payment", "how to pay",
      "what payment", "which payment", "support payment", "credit card accepted",
      "pay for subscription"],
     "payment_methods", "accepted payment methods", False),

    # Plan change — BEFORE cancel_subscription; requires entity validation
    (["switch plan", "change plan", "upgrade plan", "downgrade plan",
      "switch to", "switching to", "move to",
      "change my plan", "switch my plan", "switching my",
      "upgrade to", "downgrade to", "switch from", "change subscription",
      "switch workspace", "switching workspace"],
     "plan_change", "change / upgrade / downgrade subscription plan", True),

    # Cancel subscription
    (["cancel subscription", "cancel my subscription", "cancel my plan",
      "cancel the subscription", "end my subscription", "terminate subscription",
      "stop my subscription", "cancellation of subscription",
      "cancel my workspace", "cancel the workspace",
      "how to cancel", "to cancel my", "cancel our subscription", "cancel our plan"],
     "cancel_subscription", "cancel subscription", False),

    # Password / login
    (["reset password", "reset my password", "forgot password", "change password",
      "resetting my", "resetting the", "resetting your",
      "can't log in", "cannot log in", "locked out", "lost password",
      "forgot my password", "forgot the password"],
     "password_reset", "password reset / login recovery", False),

    # Data export
    (["export data", "export all data", "export all my data", "download my data",
      "export workspace", "bulk export", "export documents",
      "export a space", "export the space", "export as pdf", "export as zip",
      "export to pdf", "export to zip", "export a whole", "export entire",
      "download the space", "space as pdf"],
     "data_export", "export data / documents", False),

    # Permission levels
    (["permission level", "permission levels", "read-only access", "read only access",
      "view only access", "viewer role", "editor role", "commenter role",
      "what roles are", "user roles", "access level", "access levels"],
     "permission_levels", "permission levels and roles", False),

    # Feature feedback / review
    (["leave feedback", "submit feedback", "provide feedback", "give feedback",
      "leave a review", "leave feedback about", "feedback about a feature",
      "feature request", "feature suggestion", "suggest a feature"],
     "feature_feedback", "feature feedback or review", False),

    # Sign-up / account creation issues
    (["sign up", "signing up", "signup", "sign-up",
      "create an account", "creating an account", "new account setup"],
     "signup_issue", "sign-up or account creation issue", False),

    # Multiple workspace setup (no self-serve FAQ → L1)
    (["multiple workspaces", "multiple workspace", "set up workspaces",
      "setting up multiple", "create multiple workspace", "workspace for each"],
     "workspace_setup", "workspace setup / multi-workspace", False),

    # File upload errors (always L1 — FAQ doesn't resolve 40MB+ media issues)
    (["upload a file", "uploading a file", "error when uploading",
      "trouble uploading", "can't upload", "cannot upload",
      "upload error", "file upload error", "trying to upload"],
     "upload_error", "file upload error", False),

    # UI preferences / feature availability (dark mode, notifications, etc.)
    (["dark mode", "dark theme", "light mode",
      "notification frequency", "notification setting", "notify me",
      "change notification", "toggle notifications",
      "notifications stopped", "notifications not working",
      "stopped receiving notifications", "notification stopped"],
     "ui_preferences", "UI preferences / feature availability", False),

    # Account deletion
    (["delete account", "close account", "remove account", "delete my account"],
     "account_deletion", "account deletion", False),

    # Version history
    (["version history", "version histories", "restore version", "previous version",
      "old version", "document history", "history beyond", "extend.*history",
      "version beyond", "90 days", "1 year.*history", "history for compliance"],
     "version_history", "version history / document restore", False),

    # SLA / uptime
    # "sla" alone is a substring of "Slack" — use context-anchored phrases only.
    (["our sla", "your sla", "the sla", "sla breach", "sla violation",
      "sla guarantee", "sla terms", "violating sla", "breaching sla",
      "uptime", "service level", "downtime", "availability guarantee"],
     "sla_uptime", "SLA / uptime guarantee", False),

    # Invoice customization — BEFORE invoice_download ("invoice" keyword shared)
    (["customize our invoice", "customize the invoice", "customize my invoice",
      "customizing our invoice", "customizing the invoice",
      "invoice to include", "invoice with our company", "company name on invoice",
      "invoice branding", "invoice logo", "invoice template",
      "invoice with our vat", "vat on invoice", "vat invoice",
      "add our vat number", "add vat number", "add our vat",
      "include vat number", "include our vat"],
     "invoice_customize", "invoice customization", False),

    # Invoice download
    (["invoice", "receipt", "billing history", "download invoice",
      "tax receipt", "vat invoice"],
     "invoice_download", "invoice download / billing history", False),

    # SSO broken / not working — BEFORE sso_setup (more specific; same exclusive group)
    (["sso stopped", "sso not working", "sso login stopped", "sso broken",
      "sso no longer", "sso login failed", "login via sso not",
      "stopped working with sso", "sso login not working",
      "sso login has been broken", "sso is broken", "sso login broken",
      "sso keeps failing", "sso access broken", "sso has been broken"],
     "sso_issue", "SSO broken / not working", False),

    # SSO / identity provider setup
    (["sso", "single sign-on", "single sign on", "saml", "okta", "azure ad",
      "identity provider", "idp", "set up sso", "enable sso", "configure sso"],
     "sso_setup", "SSO / identity provider setup", False),

    # Audit logs
    (["audit log", "audit logs", "access audit", "set up audit", "audit trail",
      "compliance log", "activity log", "user activity logs"],
     "audit_logs", "audit logs / activity trail", False),
]


class NormalizedIntent(TypedDict):
    intent_id: str           # stable enum key → used by INTENT_FAQ_MAP
    canonical_query: str     # human-readable label for logging only
    intent_type: str         # broad category: billing | account | cancellation | contract | unknown
    confidence: float
    missing_entity: bool
    requires_clarification: bool
    unknown_entity: str      # populated when missing_entity=True


def _check_unknown_plan(query: str) -> str | None:
    words = set(query.lower().split())
    match = words.intersection(_UNKNOWN_PLAN_SIGNALS)
    return next(iter(match)) if match else None


# ── Intent class sets (for Milestone B routing policy) ───────────────────────
# Used by reasoner.py to apply intent-class aware churn escalation gate.
# Single source of truth: if an intent moves category, update here only.

TECHNICAL_INTENTS: frozenset[str] = frozenset({
    "upload_error",    # file/media upload failures
    "sso_issue",       # SSO broken / not working
    "signup_issue",    # account creation / sign-up failure
    "ui_preferences",  # feature stopped working (notifications, display)
})

BILLING_INTENTS: frozenset[str] = frozenset({
    "payment_methods",
    "cancellation_fee",
    "refund_eligibility",
    "refund_status",
    "invoice_customize",
    "invoice_download",
    # sla_uptime is contract class, not billing — handled by sla_signal in reasoner
})

CANCEL_INTENTS: frozenset[str] = frozenset({
    "cancel_subscription",
    "account_deletion",
})


_INTENT_TYPE_MAP = {
    "payment_methods":    "billing",
    "cancellation_fee":   "billing",
    "refund_eligibility": "billing",
    "refund_status":      "billing",
    "invoice_customize":  "billing",
    "invoice_download":   "billing",
    "plan_change":        "account",
    "cancel_subscription":"cancellation",
    "password_reset":     "account",
    "data_export":        "account",
    "permission_levels":  "account",
    "feature_feedback":   "other",
    "version_history":    "account",
    "sso_issue":          "technical",
    "sso_setup":          "account",
    "audit_logs":         "account",
    "signup_issue":       "account",
    "workspace_setup":    "account",
    "upload_error":       "technical",
    "ui_preferences":     "other",
    "account_deletion":   "cancellation",
    "sla_uptime":         "contract",
    "unknown_plan":       "account",
    "unknown":            "unknown",
}


# ── Multi-intent support (v8) ─────────────────────────────────────────────────
#
# Mutually exclusive pairs: within each group, only the first match fires.
# Intent IDs in different groups can co-occur freely.
#
# Rationale: refund_status and refund_eligibility are semantically exclusive
# (status check vs policy question); invoice_customize and invoice_download share
# "invoice" but are different actions. sso_issue and sso_setup share "sso" but
# indicate different situations (broken vs setup).

_EXCLUSIVE_GROUPS: list[frozenset] = [
    frozenset({"refund_status", "refund_eligibility"}),
    frozenset({"invoice_customize", "invoice_download"}),
    frozenset({"cancellation_fee", "cancel_subscription"}),
    frozenset({"sso_issue", "sso_setup"}),
]

# Precompiled at module load: O(1) group lookup per intent_id at runtime.
# (Avoids O(rules × groups) linear scan inside the hot normalize_multi loop.)
_INTENT_TO_GROUP: dict[str, int] = {
    intent: i
    for i, group in enumerate(_EXCLUSIVE_GROUPS)
    for intent in group
}


def normalize_multi(query: str) -> dict:
    """
    Scan ALL rules; return every matching intent (multi-intent aware).

    Conflict resolution: within each _EXCLUSIVE_GROUP, only the first match fires.
    Cross-group matches accumulate freely (e.g. cancel + invoice both returned).

    Returns:
      {
        "intent_set":            list[str],   # all matched intents; ["unknown"] on LLM fallback
        "requires_clarification": bool,
        "unknown_entity":        str,
        "intent_type":           str,         # type of first matched intent
        "confidence":            float,
      }
    """
    q_lower = query.lower()

    matched: list[str] = []
    fired_groups: set[int] = set()

    for keywords, intent_id, canonical, needs_entity_check in _RULES:
        if not any(kw in q_lower for kw in keywords):
            continue

        # O(1) group lookup — precompiled at module load
        group_idx = _INTENT_TO_GROUP.get(intent_id)
        if group_idx is not None and group_idx in fired_groups:
            continue

        if needs_entity_check:
            unknown = _check_unknown_plan(q_lower)
            if unknown:
                return {
                    "intent_set": ["unknown_plan"],
                    "requires_clarification": True,
                    "unknown_entity": unknown,
                    "intent_type": _INTENT_TYPE_MAP["unknown_plan"],
                    "confidence": 0.9,
                }

        matched.append(intent_id)
        if group_idx is not None:
            fired_groups.add(group_idx)

    if not matched:
        inl = _llm_normalize(query)
        return {
            "intent_set": [inl["intent_id"]],
            "requires_clarification": inl["requires_clarification"],
            "unknown_entity": inl.get("unknown_entity", ""),
            "intent_type": inl["intent_type"],
            "confidence": inl["confidence"],
        }

    return {
        "intent_set": matched,
        "requires_clarification": False,
        "unknown_entity": "",
        "intent_type": _INTENT_TYPE_MAP.get(matched[0], "unknown"),
        "confidence": 0.95,
    }


def _llm_normalize(query: str) -> NormalizedIntent:
    """LLM fallback for queries not matched by any rule."""
    try:
        from llm import call_llm, safe_json_parse
        system = (
            "You are a query normalizer for a SaaS support system. "
            "Output a canonical form and intent type for the support ticket.\n\n"
            "Output JSON only:\n"
            '{"canonical_query": "<simplified plain-English query>", '
            '"intent_type": "<billing|account|cancellation|technical|contract|unknown>", '
            '"missing_entity": false, "requires_clarification": false}'
        )
        raw = call_llm(system, f"Query: {query}")
        result = safe_json_parse(raw)
        return NormalizedIntent(
            intent_id="unknown",
            canonical_query=result.get("canonical_query", query),
            intent_type=result.get("intent_type", "unknown"),
            confidence=0.7,
            missing_entity=result.get("missing_entity", False),
            requires_clarification=result.get("requires_clarification", False),
            unknown_entity="",
        )
    except Exception:
        return NormalizedIntent(
            intent_id="unknown",
            canonical_query=query,
            intent_type="unknown",
            confidence=0.4,
            missing_entity=False,
            requires_clarification=False,
            unknown_entity="",
        )


def normalize(query: str) -> NormalizedIntent:
    """
    Compile raw user query into system ontology.

    Rule-first (O(rules) substring scan), LLM fallback for no-match.
    Returns intent_id — a stable enum key used by INTENT_FAQ_MAP for
    deterministic FAQ lookup (no embedding for covered intents).
    """
    q_lower = query.lower()

    for keywords, intent_id, canonical, needs_entity_check in _RULES:
        if any(kw in q_lower for kw in keywords):
            if needs_entity_check:
                unknown = _check_unknown_plan(q_lower)
                if unknown:
                    return NormalizedIntent(
                        intent_id="unknown_plan",
                        canonical_query=canonical,
                        intent_type=_INTENT_TYPE_MAP["unknown_plan"],
                        confidence=0.9,
                        missing_entity=True,
                        requires_clarification=True,
                        unknown_entity=unknown,
                    )
            return NormalizedIntent(
                intent_id=intent_id,
                canonical_query=canonical,
                intent_type=_INTENT_TYPE_MAP.get(intent_id, "unknown"),
                confidence=0.95,
                missing_entity=False,
                requires_clarification=False,
                unknown_entity="",
            )

    return _llm_normalize(query)
