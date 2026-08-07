"""Context projection — specialists see only what they need.

project_for_* returns typed, minimal inputs from the shared runtime state.
They never expose the full state, authorization, side-effect capability,
idempotency keys, or unrelated sender private fields.
"""
from __future__ import annotations

from ..specialists.contracts import KnowledgeSpecialistInput, SupportSpecialistInput
from .state import SharedRuntimeState

# Fields a Support specialist may see from a sender context. Deliberately
# excludes PII / account secrets / unrelated domain fields.
_SUPPORT_SENDER_ALLOWLIST = ("plan", "region", "role")


def project_for_knowledge(state: SharedRuntimeState, intent_slice: dict) -> KnowledgeSpecialistInput:
    return KnowledgeSpecialistInput(
        request_id=state.request.request_id,
        query=intent_slice.get("query", state.request.raw_text),
        intent=intent_slice.get("intent", "unknown"),
        top_k=3,
    )


def project_for_support(
    state: SharedRuntimeState, intent_slice: dict, evidence: list[dict]
) -> SupportSpecialistInput:
    ctx = state.request.sender_context
    sender_view = None
    if isinstance(ctx, dict):
        sender_view = {k: ctx[k] for k in _SUPPORT_SENDER_ALLOWLIST if k in ctx}
    history = {"ticket_count": len(state.request.message_history or [])}
    return SupportSpecialistInput(
        request_id=state.request.request_id,
        text=intent_slice.get("query", state.request.raw_text),
        intents=[intent_slice.get("intent", "unknown")],
        evidence=evidence,
        sender_context=sender_view,
        history=history,
    )
