"""Bounded tool loop used by SUPPORT_AGENT_MODE=tool_loop."""
from __future__ import annotations

import os
import sys
import time
import uuid
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Literal

# Existing modules support both `python agent/...` and `python -m agent...`.
# Keep their historical flat-import compatibility while this module is package-safe.
sys.path.insert(0, os.path.dirname(__file__))
from .reasoner import compute_l2_signals, synthesize
from .function_calling import NativeFunctionCallingAdapter, ToolCallingModel
from .grounding_compiler import compile_grounding
from .tooling import ToolGateway, ToolRuntime, ToolStatus


@dataclass
class AgentRunState:
    run_id: str
    ticket_id: str
    agent_mode: str
    tool_backend: str
    messages: list[dict]
    tool_executions: list[dict] = field(default_factory=list)
    collected_evidence: list[dict] = field(default_factory=list)
    risk_state: dict = field(default_factory=dict)
    turn_count: int = 0
    tool_call_count: int = 0
    pending_action: str | None = None
    stop_reason: str | None = None
    final_proposal: str | None = None
    final_authorization_decision: str | None = None


def _tool_message(call_id: str, result) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": result.model_dump_json()}


def _next_turn_before_deadline(model, messages: list[dict], tools: list[dict], timeout: float):
    """Bound synchronous adapters without waiting for a timed-out worker."""
    outcome: queue.Queue = queue.Queue(maxsize=1)
    def invoke():
        try:
            outcome.put(("ok", model.next_turn(messages, tools)))
        except TimeoutError:
            outcome.put(("timeout", None))
        except Exception:
            outcome.put(("error", None))
    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    try:
        return outcome.get(timeout=max(timeout, 0.001))
    except queue.Empty:
        return "deadline", None


def _log_final_decision(ledger, ticket_id: str, state: AgentRunState, result: dict) -> None:
    if ledger is None:
        return
    ledger.log_step(ticket_id, "tool_loop_final_decision", {
        "stop_reason": state.stop_reason,
        "authorization_result": result.get("action"),
        "final_action": result.get("action"),
        "grounding": result.get("grounding_check", {}),
        "risk": state.risk_state,
        "tool_call_count": state.tool_call_count,
        "turn_count": state.turn_count,
        "fallback_reason": state.stop_reason,
        "auto_reply_allowed": result.get("action") == "AUTO_REPLY",
    })


def run_tool_loop(
    ticket_text: str, ticket_id: str, user_id: str, memory, customer_context: dict | None = None,
    *, model: ToolCallingModel | None = None, backend: Literal["local", "mcp"] | None = None,
    max_turns: int = 4, max_tool_calls: int = 6, run_timeout_seconds: float = 15.0,
    tool_timeout_seconds: float = 3.0, ledger=None,
    classification: dict | None = None, tone: dict | None = None,
) -> tuple[dict, AgentRunState]:
    """Run model-driven read-only retrieval, then re-apply deterministic gates."""
    backend = backend or os.getenv("SUPPORT_TOOL_BACKEND", "local")
    signals = compute_l2_signals(ticket_text)
    state = AgentRunState(run_id=uuid.uuid4().hex, ticket_id=ticket_id, agent_mode="tool_loop", tool_backend=backend,
        messages=[{"role": "system", "content": "You may call read-only support tools. Never claim authorization; finish with a concise evidence-bounded proposal."}, {"role": "user", "content": ticket_text}], risk_state=signals)
    if signals["sla_signal"] or signals["hidden_cancel_signal"]:
        state.stop_reason = "pre_guard_escalation"
        result = synthesize(ticket_text, classification or {}, [], {}, {}, tone or {}, grounding_check=None, precomputed_signals=signals, customer_context=customer_context, no_service=True)
        result.update({"ticket_id": ticket_id, "tool_run": state.__dict__})
        _log_final_decision(ledger, ticket_id, state, result)
        return result, state

    gateway = ToolGateway(backend=backend, tool_timeout_seconds=tool_timeout_seconds, ledger=ledger)
    runtime = ToolRuntime(user_id=user_id, ticket_text=ticket_text, ticket_id=ticket_id, customer_context=customer_context, memory=memory)
    model = model or NativeFunctionCallingAdapter()
    seen: set[tuple[str, str]] = set()
    started = time.monotonic()
    while state.turn_count < max_turns and state.tool_call_count < max_tool_calls and time.monotonic() - started < run_timeout_seconds:
        state.turn_count += 1
        remaining = run_timeout_seconds - (time.monotonic() - started)
        model_status, turn = _next_turn_before_deadline(
            model, state.messages, [item.openai_schema() for item in gateway.available_tools()], remaining
        )
        if model_status != "ok":
            state.stop_reason = {
                "timeout": "provider_timeout", "deadline": "runtime_deadline_exceeded",
                "error": "provider_error",
            }[model_status]
            break
        if not turn.tool_calls:
            state.final_proposal = turn.content or ""
            state.stop_reason = "final_output"
            break
        state.messages.append({"role": "assistant", "content": turn.content, "tool_calls": [{"id": call.call_id, "type": "function", "function": {"name": call.name, "arguments": __import__("json").dumps(call.arguments)}} for call in turn.tool_calls]})
        for call in turn.tool_calls:
            if state.tool_call_count >= max_tool_calls:
                state.stop_reason = "max_tool_calls_exceeded"; break
            fingerprint = (call.name, __import__("json").dumps(call.arguments, sort_keys=True))
            if fingerprint in seen:
                state.stop_reason = "duplicate_tool_call"; break
            seen.add(fingerprint); state.tool_call_count += 1
            result = gateway.execute(call.call_id, call.name, call.arguments, runtime, state.turn_count)
            state.tool_executions.append({"call_id": call.call_id, "tool_name": call.name, "backend": backend, "status": result.status.value, "error_code": result.error_code})
            state.collected_evidence.extend(item.model_dump() for item in result.evidence)
            state.messages.append(_tool_message(call.call_id, result))
            if result.status in {ToolStatus.TIMEOUT, ToolStatus.ERROR}:
                state.stop_reason = "tool_timeout" if result.status == ToolStatus.TIMEOUT else "tool_error"; break
        if state.stop_reason: break
    if state.stop_reason is None:
        if time.monotonic() - started >= run_timeout_seconds:
            state.stop_reason = "run_timeout_exceeded"
        elif state.turn_count >= max_turns:
            state.stop_reason = "max_turns_exceeded"
        else:
            state.stop_reason = "max_tool_calls_exceeded"

    kb_results, history = [], {}
    for message in state.messages:
        if message.get("role") != "tool": continue
        import json
        payload = json.loads(message["content"])
        if payload.get("status") != "success": continue
        data = payload.get("data")
        if isinstance(data, list): kb_results = data
        elif isinstance(data, dict) and "past_tickets" in data: history = data
    draft = {"reply": state.final_proposal or ""}
    # The authoritative compiler receives only KB tool results whose evidence
    # explicitly identifies a knowledge-base source. Context/history data never
    # become grounding evidence merely because they are tool output.
    kb_evidence_ids = {item["source_id"] for item in state.collected_evidence if item.get("source_type") == "knowledge_base"}
    grounded_kb = [row for row in kb_results if row.get("doc_id") in kb_evidence_ids]
    grounding_check = compile_grounding(draft["reply"], grounded_kb, no_service=True)
    result = synthesize(ticket_text, classification or {}, grounded_kb, history, draft,
                        tone or {}, grounding_check=grounding_check,
                        precomputed_signals=signals, customer_context=customer_context,
                        no_service=True)
    # A failed/limited tool loop can never loosen the formal authorization gate.
    if state.stop_reason != "final_output" and result["action"] == "AUTO_REPLY":
        result["action"] = "ESCALATE_L1"; result.setdefault("reason_codes", []).append("tool_loop_incomplete")
    state.final_authorization_decision = result["action"]
    result.update({"ticket_id": ticket_id, "tool_run": state.__dict__})
    _log_final_decision(ledger, ticket_id, state, result)
    return result, state
