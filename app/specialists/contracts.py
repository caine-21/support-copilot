"""Specialist lane contracts.

Each specialist has an independent input/output contract, its own allowed
context, read-only capabilities, a completion condition and a failure
contract. A specialist may propose an action but never authorize one.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SpecialistStatus(str, Enum):
    SUCCESS = "success"
    NO_EVIDENCE = "no_evidence"
    BLOCKED = "blocked"
    ERROR = "error"


class KnowledgeSpecialistInput(BaseModel):
    request_id: str
    query: str
    intent: str
    top_k: int = 3


class KnowledgeSpecialistResult(BaseModel):
    request_id: str
    intent: str
    evidence: list[dict] = Field(default_factory=list)  # [{"doc_id","snippet","score",...}]
    coverage: str = "none"  # full | partial | none
    source_refs: list[str] = Field(default_factory=list)
    status: SpecialistStatus = SpecialistStatus.SUCCESS
    reason_codes: list[str] = Field(default_factory=list)
    skill_name: str | None = None
    skill_status: str | None = None
    skill_reason_codes: list[str] = Field(default_factory=list)


class SupportSpecialistInput(BaseModel):
    request_id: str
    text: str
    intents: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    sender_context: dict | None = None
    history: dict = Field(default_factory=dict)


class SupportSpecialistResult(BaseModel):
    request_id: str
    intents: list[str] = Field(default_factory=list)
    proposal: dict = Field(default_factory=dict)  # {"draft": str, "grounded": bool, ...}
    confidence: float = 0.0
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    status: SpecialistStatus = SpecialistStatus.SUCCESS
