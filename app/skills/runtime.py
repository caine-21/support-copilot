"""Skill runtime.

A Skill executes through the SAME scoped gateway its Specialist was given, so
the effective capability is Specialist scope ∩ Skill allowed_tools. A Skill
never constructs a backend, never sees an authorization, and can never grant
an action.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .contracts import SkillResult, SkillStatus
from .registry import get


def run_skill(spec, context: dict[str, Any], gateway) -> SkillResult:
    """Dispatch by skill name. context must already be the minimal projection."""
    if spec.name == "knowledge_lookup":
        return _run_knowledge_lookup(spec, context, gateway)
    return SkillResult(skill_name=spec.name, status=SkillStatus.ERROR, reason_codes=["unknown_skill_impl"])


def _status_value(result) -> str | None:
    status = getattr(result, "status", None)
    return getattr(status, "value", None) if status is not None else None


def _run_knowledge_lookup(spec, context: dict[str, Any], gateway) -> SkillResult:
    from agent.tooling import ToolRuntime

    query = context.get("query", "")
    top_k = context.get("top_k", 3)
    intent = context.get("intent", "unknown")
    try:
        result = gateway.execute(
            "a1-skill-kb",
            "search_knowledge_base",
            {"query": query, "top_k": top_k},
            ToolRuntime(user_id=context.get("request_id", "?"), ticket_text=query),
            turn_index=0,
        )
    except Exception as exc:  # fail closed: an exception is never success
        return SkillResult(skill_name=spec.name, status=SkillStatus.ERROR,
                           reason_codes=[f"tool_exception:{type(exc).__name__}"])

    sv = _status_value(result)
    if sv != "success":
        if sv == "not_found":
            return SkillResult(skill_name=spec.name, status=SkillStatus.NO_EVIDENCE,
                               reason_codes=["no_kb_evidence"])
        return SkillResult(skill_name=spec.name, status=SkillStatus.ERROR,
                           reason_codes=[f"tool_{sv}:{getattr(result, 'error_code', '')}"])

    rows = result.data or []
    if not rows:
        return SkillResult(skill_name=spec.name, status=SkillStatus.NO_EVIDENCE,
                           reason_codes=["no_kb_evidence"])

    from agent.kb import INTENT_FAQ_MAP

    doc_ids = INTENT_FAQ_MAP.get(intent, [])
    if doc_ids:
        selected = [r for r in rows if r.get("doc_id") in doc_ids]
        if selected:
            covered = len({r.get("doc_id") for r in selected}) >= len(doc_ids)
            return SkillResult(
                skill_name=spec.name, status=SkillStatus.SUCCESS,
                data={"evidence": selected, "coverage": "full" if covered else "partial"},
                evidence_refs=[r["doc_id"] for r in selected],
                reason_codes=["intent_faq_selected"],
            )
    return SkillResult(
        skill_name=spec.name, status=SkillStatus.SUCCESS,
        data={"evidence": rows, "coverage": "partial"},
        evidence_refs=[r["doc_id"] for r in rows],
        reason_codes=["kb_fallback"],
    )


# ── knowledge_lookup skill contract ─────────────────────────────────────────


class _Input(BaseModel):
    request_id: str
    query: str
    intent: str
    top_k: int = 3


class _Output(BaseModel):
    evidence: list[dict] = []
    coverage: str = "none"


class knowledge_lookup:
    """The knowledge_lookup SkillSpec (contract refs for the registry)."""

    Input = _Input
    Output = _Output
