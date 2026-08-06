"""Shared offline helpers for service/ tests (fake decision port)."""
from __future__ import annotations

from typing import Any, Optional


def make_fake_decision_fn(
    *,
    action: str = "AUTO_REPLY",
    reason: str = "confidence=0.8, KB strong-grounded",
    grounding: str = "strong",
    grounding_safe: bool = True,
    draft: str = "Thanks — here is how to reset your password: [KB]",
    kb: Optional[list[dict]] = None,
    raise_error: Optional[Exception] = None,
):
    """Return a decision port that mimics agent_loop.run_agent's result dict."""

    def fake(
        ticket_text: str,
        ticket_id: str,
        user_id: str,
        customer_context: Optional[dict[str, Any]] = None,
        ledger: Any = None,
    ) -> dict[str, Any]:
        if raise_error is not None:
            raise raise_error
        return {
            "action": action,
            "reason": reason,
            "confidence": 0.8 if action == "AUTO_REPLY" else 0.6,
            "grounding": grounding,
            "priority": "low" if action == "AUTO_REPLY" else "high",
            "intent": "password_reset",
            "tone": "neutral",
            "churn_risk": 0.1,
            "kb_grounding": kb or [
                {"doc_id": "FAQ-password-reset", "snippet": "How to reset your password."}
            ],
            "grounding_check": {
                "grounding_ratio": 1.0 if grounding_safe else 0.5,
                "auto_reply_safe": grounding_safe,
                "ungrounded_claims": [] if grounding_safe else ["unsafe claim"],
            },
            "draft_reply": draft,
            "routing_signals": [] if action == "AUTO_REPLY" else ["churn_risk_high"],
            "intent_set": ["password_reset"],
            "missing_info": [],
            "assumption_replay": {"changed": False},
        }

    return fake
