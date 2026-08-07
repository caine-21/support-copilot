"""Knowledge Specialist: retrieve KB evidence for an intent via a Skill.

Uses an INJECTED scoped tool gateway (local or MCP backend) — the specialist
never reads env, never selects a backend, never constructs an MCP client.
Task capability is delegated to a deterministic-selected Skill
(KnowledgeLookupSkill); the Skill executes through the SAME scoped gateway, so
effective capability is Specialist scope ∩ Skill allowed_tools. Transport
failures keep their semantics (ERROR); a genuine empty KB is NO_EVIDENCE.
"""
from __future__ import annotations

from .contracts import (
    KnowledgeSpecialistInput,
    KnowledgeSpecialistResult,
    SpecialistStatus,
)


def run_knowledge_specialist(kinput: KnowledgeSpecialistInput, *, gateway) -> KnowledgeSpecialistResult:
    """gateway: a scoped tool gateway with .execute(call_id, tool_name, raw_args,
    runtime, turn_index) returning a ToolResult-compatible object (.status/.data)."""
    from app.skills.contracts import SkillStatus
    from app.skills.registry import get
    from app.skills.runtime import run_skill
    from app.skills.selector import select_skills

    sel = select_skills(specialist="knowledge", intent_set=[kinput.intent])
    if not sel.selected_skills:
        # Explicit NO_SKILL → existing fallback. Never a random/default Skill.
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            status=SpecialistStatus.NO_EVIDENCE,
            reason_codes=["no_skill"],
            skill_name=None,
            skill_status=None,
        )

    spec = get(sel.selected_skills[0])
    # Skill context is the minimal projection (⊆ specialist context).
    context = {
        "request_id": kinput.request_id,
        "query": kinput.query,
        "intent": kinput.intent,
        "top_k": kinput.top_k,
    }
    result = run_skill(spec, context, gateway)
    return _map_skill_result(kinput, spec.name, result)


def _map_skill_result(kinput: KnowledgeSpecialistInput, skill_name: str, result) -> KnowledgeSpecialistResult:
    from app.skills.contracts import SkillStatus

    status = result.status
    if status is SkillStatus.SUCCESS:
        data = result.data or {}
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            evidence=data.get("evidence", []),
            coverage=data.get("coverage", "none"),
            source_refs=result.evidence_refs,
            status=SpecialistStatus.SUCCESS,
            reason_codes=result.reason_codes,
            skill_name=skill_name,
            skill_status=status.value,
            skill_reason_codes=result.reason_codes,
        )
    if status is SkillStatus.NO_EVIDENCE:
        return KnowledgeSpecialistResult(
            request_id=kinput.request_id,
            intent=kinput.intent,
            status=SpecialistStatus.NO_EVIDENCE,
            reason_codes=result.reason_codes,
            skill_name=skill_name,
            skill_status=status.value,
            skill_reason_codes=result.reason_codes,
        )
    return KnowledgeSpecialistResult(
        request_id=kinput.request_id,
        intent=kinput.intent,
        status=SpecialistStatus.ERROR,
        reason_codes=result.reason_codes,
        skill_name=skill_name,
        skill_status=status.value,
        skill_reason_codes=result.reason_codes,
    )
