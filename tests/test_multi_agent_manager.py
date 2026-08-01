import pytest
from agent.multi_agent.manager import decide_manager
from conftest import manager


@pytest.mark.parametrize("selected", [["billing"], ["technical"], ["billing", "technical"], []])
def test_valid_manager_selection_is_preserved(selected):
    decision, errors = decide_manager({"classification": {}}, manager(selected))
    assert decision.selected_specialists == selected and not errors


@pytest.mark.parametrize("output", ["not json", {"selected_specialists": ["unknown"], "confidence": 1}, RuntimeError("boom")])
def test_invalid_or_failed_manager_uses_recorded_fallback(output):
    def runner(_):
        if isinstance(output, Exception): raise output
        return output
    decision, errors = decide_manager({"classification": {"intent": "billing"}}, runner)
    assert decision.selected_specialists == ["billing"]
    assert "manager_fallback_used" in decision.reason_codes and "domain_slice_fallback_used" in decision.reason_codes and errors
