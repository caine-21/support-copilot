from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

SpecialistName = Literal["billing", "technical"]
Route = Literal["no_change", "escalate_l1", "escalate_l2"]

class DomainTicketSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specialist: SpecialistName
    excerpts: list[str] = Field(default_factory=list, max_length=4)
    reason_codes: list[str] = Field(default_factory=list)
    @field_validator("excerpts")
    @classmethod
    def bounded_unique_excerpts(cls, value):
        if len(value) != len(set(value)) or any(not item.strip() or len(item) > 500 for item in value):
            raise ValueError("excerpts must be unique, non-empty, and <= 500 chars")
        return value

class SafeAgentError(BaseModel):
    component: Literal["manager", "billing", "technical", "merger", "eval"]
    code: str
    retryable: bool = False

class ManagerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_specialists: list[SpecialistName] = Field(max_length=2)
    domain_slices: list[DomainTicketSlice] = Field(default_factory=list, max_length=2)
    detected_domains: list[str] = Field(default_factory=list)
    multi_intent: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    @field_validator("selected_specialists")
    @classmethod
    def unique_specialists(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("selected_specialists must be unique")
        return value
    @field_validator("domain_slices")
    @classmethod
    def unique_slice_specialists(cls, value):
        if len({item.specialist for item in value}) != len(value):
            raise ValueError("domain slices must be unique by specialist")
        return value

class SpecialistResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specialist: SpecialistName
    applicable: bool
    issue_types: list[str] = Field(default_factory=list)
    verified_facts: list[str] = Field(default_factory=list)
    evidence_doc_ids: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    proposed_answer_points: list[str] = Field(default_factory=list)
    recommended_route: Route = "no_change"
    confidence: float = Field(ge=0, le=1)
    domain_leakage_flags: list[str] = Field(default_factory=list)
    error: SafeAgentError | None = None

class MultiAgentShadowPacket(BaseModel):
    mode: Literal["shadow"] = "shadow"
    status: Literal["completed", "partial", "failed", "skipped"]
    manager_decision: ManagerDecision | None = None
    specialist_results: list[SpecialistResult] = Field(default_factory=list)
    merged_facts: list[str] = Field(default_factory=list)
    merged_missing_information: list[str] = Field(default_factory=list)
    merged_risk_flags: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    shadow_recommended_route: Route = "no_change"
    baseline_action: str
    baseline_action_unchanged: bool
    skip_reason: str | None = None
    errors: list[SafeAgentError] = Field(default_factory=list)
