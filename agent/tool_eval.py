"""Deterministic orchestration/contract metrics for scripted tool-loop scenarios."""
from __future__ import annotations
import json
import sys

def evaluate_tool_runs(cases: list[dict]) -> dict:
    total = len(cases) or 1
    def rate(key): return sum(bool(case.get(key)) for case in cases) / total
    calls = [case.get("tool_calls", 0) for case in cases]
    return {
        "case_count": len(cases),
        "tool_selection_accuracy": rate("tool_selection_correct"),
        "argument_validity_rate": rate("arguments_valid"),
        "multi_step_task_success": rate("multi_step_success"),
        "unnecessary_tool_call_rate": sum(bool(case.get("unnecessary_tool_call")) for case in cases) / total,
        "loop_termination_rate": rate("terminated"),
        "local_mcp_contract_parity": rate("contract_parity"),
        "grounded_final_response_rate": rate("grounded_final"),
        "unsafe_action_count": sum(bool(case.get("unsafe_action")) for case in cases),
        "unsafe_auto_reply_count": sum(bool(case.get("unsafe_auto_reply")) for case in cases),
        "average_tool_calls": sum(calls) / total,
        "evidence_boundary": "scripted orchestration/contract eval; not real-model accuracy",
    }


def main() -> int:
    # Deliberately scripted: this checks orchestration contracts only and does
    # not load providers, configuration, or write a report file.
    report = evaluate_tool_runs([{
        "tool_selection_correct": True, "arguments_valid": True,
        "multi_step_success": True, "terminated": True,
        "contract_parity": True, "grounded_final": True, "tool_calls": 2,
    }])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["unsafe_action_count"] == 0 and report["unsafe_auto_reply_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
