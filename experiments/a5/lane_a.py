"""Lane A — deterministic workflow (current A1-A4 main path).

Kept as-is; not wrapped into an "agent". Produces a uniform ExperimentResult.
"""
from __future__ import annotations

import time

from app.contracts.incoming_request import Channel, IncomingRequest
from app.runtime.run_a1 import run_a1

from .contracts import ExperimentResult


def lane_a(case: dict) -> ExperimentResult:
    req = IncomingRequest(
        request_id=f"A5-{case['case_id']}",
        channel=Channel.TICKET,
        raw_text=case["input"],
        sender_context=case.get("context"),
    )
    t0 = time.monotonic()
    r = run_a1(req)
    latency_ms = round((time.monotonic() - t0) * 1000, 2)
    tools = [e["payload"].get("tool") for e in r.trace if e["event_type"] == "tool_called"]
    return ExperimentResult(
        case_id=case["case_id"], lane="A",
        predicted_intents=r.intents,
        tools_requested=tools,
        tools_completed=tools,
        evidence_refs=r.evidence_summary.get("doc_ids", []),
        final_authorization=r.authorization_status,
        unsafe_action=(
            r.authorization_status == "AUTO_REPLY"
            and r.grounding_status.get("auto_reply_safe") is not True
        ),
        latency_ms=latency_ms,
        model_calls=0,  # deterministic facade; internal LLM (if any) not instrumented
        input_tokens=0,
        output_tokens=0,
        trace_event_count=len(r.trace),
        error_codes=[e.get("reason_codes", [""])[0] for e in r.trace if e.get("reason_codes")],
    )
