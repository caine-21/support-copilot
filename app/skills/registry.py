"""Static Skill registry with registration-time capability validation.

Registration rejects a SkillSpec that requests tools or context beyond the
owning Specialist's capability — so a Skill can never widen what its
Specialist is allowed to see or do. The runtime additionally enforces the
same intersection through the scoped gateway (defense in depth).
"""
from __future__ import annotations

from .contracts import SkillSpec

_REGISTRY: dict[str, SkillSpec] = {}

# Context fields a Specialist may expose to its Skills (a subset of the
# runtime state). Skill required_context must be within this set.
SPECIALIST_CONTEXT_FIELDS: dict[str, set[str]] = {
    "knowledge": {"request_id", "query", "intent", "top_k"},
    "support": {"request_id", "text", "intents", "evidence", "sender_context", "history"},
}


def _specialist_tools(specialist: str) -> set[str]:
    from agent.tooling import SPECIALIST_TOOL_ALLOWLISTS

    return set(SPECIALIST_TOOL_ALLOWLISTS.get(specialist, []))


def register(spec: SkillSpec) -> None:
    """Register a SkillSpec, rejecting anything beyond Specialist capability."""
    if not spec.name or not spec.version:
        raise ValueError("skill name and version are required")
    if spec.name in _REGISTRY:
        raise ValueError(f"duplicate skill name: {spec.name}")
    capability = _specialist_tools(spec.specialist)
    for tool in spec.allowed_tools:
        if tool not in capability:
            raise ValueError(
                f"skill {spec.name} requests tool '{tool}' beyond specialist "
                f"'{spec.specialist}' capability (allowed: {sorted(capability)})"
            )
    context = SPECIALIST_CONTEXT_FIELDS.get(spec.specialist, set())
    for field in spec.required_context:
        if field not in context:
            raise ValueError(
                f"skill {spec.name} requires context field '{field}' outside "
                f"specialist '{spec.specialist}' projection"
            )
    _REGISTRY[spec.name] = spec


def get(name: str) -> SkillSpec | None:
    return _REGISTRY.get(name)


def list_skills() -> list[SkillSpec]:
    return list(_REGISTRY.values())


def _register_knowledge_lookup() -> None:
    from .runtime import knowledge_lookup

    register(
        SkillSpec(
            name="knowledge_lookup",
            version="1.0.0",
            description="Retrieve KB evidence for a ticket intent through the scoped read gateway.",
            specialist="knowledge",
            applicability={"intents": ["*"]},
            input_schema=knowledge_lookup.Input,
            output_schema=knowledge_lookup.Output,
            required_context=("request_id", "query", "intent", "top_k"),
            allowed_tools=("search_knowledge_base",),
            prompt_ref=None,  # deterministic tool skill — no LLM prompt
            policy_refs=("intent_faq_mapping", "fail_closed_grounding"),
            completion_contract={
                "SUCCESS": "retrieval/evidence valid",
                "NO_EVIDENCE": "normal query but no KB result",
                "BLOCKED": "capability violation",
                "ERROR": "tool/MCP failure",
            },
        )
    )


_register_knowledge_lookup()
