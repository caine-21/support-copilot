"""Deterministic Skill selector.

Selects Skills by specialist + intent / task type. NO LLM routing. If no
Skill applies, the selection is explicitly empty (NO_SKILL) so the caller
uses its existing fallback — there is no random/default Skill.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .registry import list_skills


class SkillSelection(BaseModel):
    selected_skills: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    inputs_used: list[str] = Field(default_factory=list)


def select_skills(*, specialist: str, intent_set: list[str], task_type: str | None = None) -> SkillSelection:
    inputs = ["specialist", "intent_set"]
    if task_type is not None:
        inputs.append("task_type")
    selected: list[str] = []
    reasons: list[str] = []
    for spec in list_skills():
        if spec.specialist != specialist:
            continue
        app = spec.applicability or {}
        if not app.get("intents"):
            continue
        if "*" in app["intents"] or any(i in app["intents"] for i in intent_set):
            selected.append(spec.name)
            reasons.append(f"{spec.name}:applicable")
    if not selected:
        return SkillSelection(selected_skills=[], reason_codes=["no_skill"], inputs_used=inputs)
    return SkillSelection(selected_skills=selected, reason_codes=reasons, inputs_used=inputs)
