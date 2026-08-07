"""Lane B — single bounded agent + READ tools (reuses tool_loop).

The agent interprets the ticket, chooses when to call read-only tools, and
assembles evidence; the final authorization comes from the SAME deterministic
gate (synthesize) inside tool_loop. No side effects, no executor visibility.
"""
from __future__ import annotations

import time

from agent.function_calling import NativeFunctionCallingAdapter
from agent.memory import AgentMemory

from .contracts import ExperimentResult


def lane_b(case: dict, *, model=None) -> ExperimentResult:
    from agent.tool_loop import run_tool_loop

    ticket = case["input"]
    memory = AgentMemory()
    t0 = time.monotonic()
    result, state = run_tool_loop(
        ticket, "T-a5-b", "U-a5", memory,
        customer_context=case.get("context"),
        model=model or NativeFunctionCallingAdapter(),
        backend="local",
        classification=None, tone=None,
    )
    latency_ms = round((time.monotonic() - t0) * 1000, 2)
    tools = [te["tool_name"] for te in state.tool_executions]
    completed = [te["tool_name"] for te in state.tool_executions if te.get("status") == "success"]
    evidence_refs = [e["source_id"] for e in state.collected_evidence]
    auth = result.get("action", "")
    return ExperimentResult(
        case_id=case["case_id"], lane="B",
        predicted_intents=result.get("intent_set", []),
        tools_requested=tools,
        tools_completed=completed,
        evidence_refs=evidence_refs,
        final_authorization=auth,
        unsafe_action=(auth == "AUTO_REPLY" and result.get("grounding_check", {}).get("auto_reply_safe") is not True),
        latency_ms=latency_ms,
        model_calls=state.turn_count,
        input_tokens=0,  # adapter does not expose token usage
        output_tokens=0,
        trace_event_count=len(state.messages),
        error_codes=[state.stop_reason] if state.stop_reason else [],
    )
