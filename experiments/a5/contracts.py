"""A5 experiment contracts.

ExperimentResult is the single per-case output of every lane. It carries
business-meaningful fields only — no private chain-of-thought.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExperimentResult(BaseModel):
    case_id: str
    lane: str  # "A" | "B" | "C"
    task_success: bool = False
    predicted_intents: list[str] = Field(default_factory=list)
    selected_specialists: list[str] = Field(default_factory=list)
    tools_requested: list[str] = Field(default_factory=list)
    tools_completed: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    final_authorization: str = ""
    unsafe_action: bool = False
    latency_ms: float = 0.0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    trace_event_count: int = 0
    error_codes: list[str] = Field(default_factory=list)
