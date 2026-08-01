import json
import pytest
from pydantic import ValidationError
from agent.multi_agent.contracts import ManagerDecision, MultiAgentShadowPacket, SpecialistResult


def test_contracts_validate_and_round_trip():
    manager = ManagerDecision(selected_specialists=["billing"], confidence=1)
    specialist = SpecialistResult(specialist="billing", applicable=True, confidence=1)
    packet = MultiAgentShadowPacket(status="completed", baseline_action="ESCALATE_L1", baseline_action_unchanged=True, manager_decision=manager, specialist_results=[specialist])
    assert MultiAgentShadowPacket.model_validate_json(packet.model_dump_json()) == packet
    assert json.loads(packet.model_dump_json())["mode"] == "shadow"


@pytest.mark.parametrize("payload", [
    {"selected_specialists": ["unknown"], "confidence": .5},
    {"selected_specialists": ["billing", "billing"], "confidence": .5},
    {"selected_specialists": ["billing", "technical", "billing"], "confidence": .5},
    {"selected_specialists": [], "confidence": 1.1},
])
def test_manager_contract_rejects_invalid_values(payload):
    with pytest.raises(ValidationError): ManagerDecision.model_validate(payload)


def test_specialist_contract_rejects_invalid_route_and_lists_are_isolated():
    with pytest.raises(ValidationError): SpecialistResult(specialist="billing", applicable=True, confidence=.5, recommended_route="refund")
    one = SpecialistResult(specialist="billing", applicable=True, confidence=.5); two = SpecialistResult(specialist="billing", applicable=True, confidence=.5)
    one.risk_flags.append("x")
    assert two.risk_flags == []
