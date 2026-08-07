"""Shared runtime state for a single A1 run.

Layers (conceptual):
  raw input      -> request
  derived facts  -> normalized_intents / risk_signals / context_status
  route          -> route_decision
  evidence       -> evidence / lane_results
  proposal       -> proposal
  authorization  -> authorization   (specialists must never write this)

Authorization is written only by the orchestrator via the existing
deterministic gate; specialists only propose.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts.incoming_request import Channel, ChannelCapability, IncomingRequest


class SharedRuntimeState(BaseModel):
    request: IncomingRequest
    capability_status: ChannelCapability
    normalized_intents: list[str] = Field(default_factory=list)
    risk_signals: dict = Field(default_factory=dict)
    context_status: dict | None = None
    route_decision: dict = Field(default_factory=dict)
    lane_results: dict = Field(default_factory=dict)  # intent -> {evidence, proposal, ...}
    evidence: list = Field(default_factory=list)
    grounding_status: dict = Field(default_factory=dict)
    proposal: dict = Field(default_factory=dict)
    authorization: dict = Field(default_factory=dict)  # final gate decision
