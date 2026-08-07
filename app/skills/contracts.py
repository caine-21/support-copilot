"""Typed Skill contracts.

SkillSpec is a static Python declaration (the runtime source of truth). A
SKILL.md is human-readable evidence only — it is never parsed for permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillStatus(str, Enum):
    SUCCESS = "success"
    NO_EVIDENCE = "no_evidence"
    BLOCKED = "blocked"
    ERROR = "error"


class SkillResult(BaseModel):
    skill_name: str
    status: SkillStatus
    data: Any = None
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class SkillSpec:
    name: str
    version: str
    description: str
    specialist: str
    applicability: dict                    # e.g. {"intents": ["*"]}
    input_schema: type[BaseModel]          # reference to the skill input model
    output_schema: type[BaseModel]         # reference to the skill result model
    required_context: tuple[str, ...]      # context fields the skill needs
    allowed_tools: tuple[str, ...]         # tools the skill may use (subset of specialist capability)
    prompt_ref: str | None = None          # reference to an existing prompt builder; None for deterministic-tool skills
    policy_refs: tuple[str, ...] = ()      # references to existing policies the skill respects
    completion_contract: dict | None = None
