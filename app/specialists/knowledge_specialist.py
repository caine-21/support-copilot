"""Knowledge Specialist: read-only KB retrieval + evidence selection.

Uses an INJECTED scoped tool gateway. The specialist never reads env vars,
never selects a backend, and never constructs an MCP client — the runtime
composition root decides transport. Transport failures keep their failure
semantics (ERROR), never degrade into an empty success. Read-only; cannot
draft or authorize.
"""
from __future__ import annotations

from .contracts import (
    KnowledgeSpecialistInput,
    KnowledgeSpecialistResult,
    SpecialistStatus,
)


def run_knowledge_specialist(kinput: KnowledgeSpecialistInput, *, gateway) -> KnowledgeSpecialistResult:
    """gateway: an object exposing execute(call_id, tool_name, raw_args, runtime, turn_index)
    returning a ToolResult-compatible object (status / data / error_code)."""
    from agent.tooling import ToolRuntime

    try:
        result = gateway.execute(
            "a1-kb",
            "search_knowledge_base",
            {"query": kinput.query, "top_k": kinput.top_k},
            ToolRuntime(user_id=kinput.request_id, ticket_text=kinput.query),
            turn_index=0,
        )
    except Exception as exc:  # fail closed: an exception is never success
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            status=SpecialistStatus.ERROR,
            reason_codes=[f"tool_exception:{type(exc).__name__}"],
        )

    status = getattr(result, "status", None)
    status_value = getattr(status, "value", None) if status is not None else None

    if status_value == "success":
        rows = result.data or []
    elif status_value == "not_found":
        # A genuine empty KB result is NO_EVIDENCE, not an error.
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            status=SpecialistStatus.NO_EVIDENCE,
            reason_codes=["no_kb_evidence"],
        )
    else:
        # Transport / permission / domain failure keeps its failure semantics.
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            status=SpecialistStatus.ERROR,
            reason_codes=[f"tool_{status_value or 'unknown'}:{getattr(result, 'error_code', '')}"],
        )

    if not rows:
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            status=SpecialistStatus.NO_EVIDENCE,
            reason_codes=["no_kb_evidence"],
        )

    from agent.kb import INTENT_FAQ_MAP

    doc_ids = INTENT_FAQ_MAP.get(kinput.intent, [])
    if doc_ids:
        selected = [r for r in rows if r.get("doc_id") in doc_ids]
        if selected:
            covered = len({r.get("doc_id") for r in selected}) >= len(doc_ids)
            return KnowledgeSpecialistResult(
                request_id=kinput.request_id,
                intent=kinput.intent,
                evidence=selected,
                coverage="full" if covered else "partial",
                source_refs=[r["doc_id"] for r in selected],
                status=SpecialistStatus.SUCCESS,
                reason_codes=["intent_faq_selected"],
            )

    return KnowledgeSpecialistResult(
        request_id=kinput.request_id,
        intent=kinput.intent,
        evidence=rows,
        coverage="partial",
        source_refs=[r["doc_id"] for r in rows],
        status=SpecialistStatus.SUCCESS,
        reason_codes=["kb_fallback"],
    )
