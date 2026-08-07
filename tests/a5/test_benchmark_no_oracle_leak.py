"""A5: the agent-visible benchmark cases must not leak oracle/gold labels."""
import json
from pathlib import Path

import pytest

BENCHMARK = Path(__file__).resolve().parents[2] / "experiments" / "a5" / "benchmark.json"

_FORBIDDEN_IN_CASE = {
    "expected_authorizations", "acceptable_authorizations", "required_intents",
    "required_evidence", "expected_route", "expected_specialist", "expected_tool",
    "oracle", "gold", "evidence_min", "context_sensitive", "risk",
}


def test_cases_do_not_leak_oracle_fields():
    bm = json.load(open(BENCHMARK, encoding="utf-8"))
    for case in bm["cases"]:
        leaked = _FORBIDDEN_IN_CASE & set(case.keys())
        assert not leaked, f"case {case['case_id']} leaks oracle fields: {leaked}"


def test_oracle_is_separate_and_complete():
    bm = json.load(open(BENCHMARK, encoding="utf-8"))
    oracle_ids = {o["case_id"] for o in bm["oracle"]}
    case_ids = {c["case_id"] for c in bm["cases"]}
    assert oracle_ids == case_ids, "oracle and cases must be 1:1"
    for o in bm["oracle"]:
        assert "acceptable_authorizations" in o
        assert "required_intents" in o
        assert "required_evidence" in o


def test_global_forbidden_tool_never_in_cases():
    bm = json.load(open(BENCHMARK, encoding="utf-8"))
    for tool in bm.get("global_forbidden_tools", []):
        for case in bm["cases"]:
            assert "tools" not in case or tool not in case["tools"]
