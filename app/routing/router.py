"""Deterministic, auditable request router. No LLM, no hidden reasoning.

Decides the execution path from facts only: channel, normalized intent set,
deterministic risk signals, and context completeness. Every route is
explainable via RouteDecision.reason_codes.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts.incoming_request import Channel, ChannelCapability, CHANNEL_CAPABILITY


class RouteDecision(BaseModel):
    selected_lanes: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    inputs_used: list[str] = Field(default_factory=list)
    blocked_lanes: list[str] = Field(default_factory=list)
    capability_status: str = ""
    early_stop: bool = False
    early_stop_reason: str | None = None
    intent_slices: list[dict] = Field(default_factory=list)  # [{"intent", "query"}]


def _make_intent_slices(intent_set: list[str], raw_text: str) -> list[dict]:
    if not intent_set:
        return [{"intent": "unknown", "query": raw_text}]
    return [{"intent": i, "query": raw_text} for i in intent_set]


def route_request(
    *,
    channel: Channel,
    intent_set: list[str],
    risk_signals: dict,
    context_status: dict | None,
    raw_text: str,
) -> RouteDecision:
    inputs = ["channel"]
    capability = CHANNEL_CAPABILITY[channel]

    # Honest three-channel boundary: email / lead are contract + routing only.
    if capability is ChannelCapability.ROUTING_ONLY:
        return RouteDecision(
            selected_lanes=[],
            reason_codes=["channel_routing_only"],
            inputs_used=inputs,
            blocked_lanes=["support", "knowledge"],
            capability_status=capability.value,
            early_stop=True,
            early_stop_reason="channel_routing_only",
        )

    inputs += ["intent_set", "risk_signals"]
    # Deterministic early-risk pre-guard (mirrors agent_loop early-L2): a
    # high-risk signal stops before any drafting / tool loop.
    if risk_signals.get("sla_signal") or risk_signals.get("hidden_cancel_signal"):
        return RouteDecision(
            selected_lanes=[],
            reason_codes=["early_risk_pre_guard"],
            inputs_used=inputs,
            blocked_lanes=["support", "knowledge"],
            capability_status=capability.value,
            early_stop=True,
            early_stop_reason="early_risk_pre_guard",
        )

    if context_status is not None:
        inputs.append("context_status")

    slices = _make_intent_slices(intent_set, raw_text)
    multi = len(slices) > 1
    return RouteDecision(
        selected_lanes=["support", "knowledge"],
        reason_codes=["multi_intent", "route_normal"] if multi else ["single_intent", "route_normal"],
        inputs_used=inputs,
        blocked_lanes=[],
        capability_status=capability.value,
        intent_slices=slices,
    )
