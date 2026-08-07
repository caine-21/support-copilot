"""Knowledge Specialist: read-only KB retrieval + evidence selection.

Reuses the existing `search_knowledge_base` tool (wraps agent.kb.search) and
the existing intent->FAQ map for per-intent evidence selection. Read-only;
cannot draft or authorize. Errors fail closed via SpecialistStatus.ERROR.
"""
from __future__ import annotations

from .contracts import (
    KnowledgeSpecialistInput,
    KnowledgeSpecialistResult,
    SpecialistStatus,
)


def _kb_search(query: str, top_k: int) -> list[dict]:
    from agent.tooling import SearchKnowledgeArgs, search_knowledge_base

    result = search_knowledge_base(SearchKnowledgeArgs(query=query, top_k=top_k), None)
    return result.data or []


def run_knowledge_specialist(kinput: KnowledgeSpecialistInput) -> KnowledgeSpecialistResult:
    try:
        rows = _kb_search(kinput.query, kinput.top_k)
    except Exception as exc:  # fail closed: an error is never success
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            status=SpecialistStatus.ERROR,
            reason_codes=[f"kb_error:{type(exc).__name__}"],
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
