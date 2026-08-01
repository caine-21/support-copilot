import pytest
from pydantic import ValidationError

from agent.multi_agent_eval import (
    MultiAgentEvalCase,
    evaluate_case,
    is_unsafe_auto_reply,
    load_cases,
    make_rate,
    observe_context_isolation,
    run_eval,
)


def _case(case_id):
    return next(case for case in load_cases() if case.case_id == case_id)


def test_all_fixtures_use_the_strict_explicit_schema():
    cases = load_cases()
    assert len(cases) == 20


@pytest.mark.parametrize(
    "field",
    ["business_oracle", "injected_behavior", "expected_observation", "oracle_source", "oracle_notes"],
)
def test_missing_explicit_oracle_field_is_not_legacy_compatible(field):
    payload = _case("billing_only").model_dump()
    payload.pop(field)
    with pytest.raises(ValidationError):
        MultiAgentEvalCase.model_validate(payload)


def test_case_id_does_not_control_early_l2_or_manager_error_behavior():
    early = evaluate_case(_case("baseline_l2").model_copy(update={"case_id": "renamed_case"}))
    ordinary = evaluate_case(_case("billing_only").model_copy(update={"case_id": "baseline_l2"}))
    invalid_json = evaluate_case(_case("invalid_manager_json").model_copy(update={"case_id": "renamed_json"}))
    invalid_schema = evaluate_case(_case("invalid_manager_schema").model_copy(update={"case_id": "renamed_schema"}))

    assert early["baseline_action"] == "ESCALATE_L2"
    assert early["packet"]["status"] == "skipped"
    assert early["calls"] == {"manager": 0, "billing": 0, "technical": 0}
    assert ordinary["baseline_action"] != "ESCALATE_L2"
    assert "manager_json_invalid" in [error["code"] for error in invalid_json["packet"]["errors"]]
    assert "manager_schema_invalid" in [error["code"] for error in invalid_schema["packet"]["errors"]]


def test_zero_denominator_metrics_are_explicitly_non_applicable():
    assert make_rate(0, 0) == {
        "value": None,
        "numerator": 0,
        "denominator": 0,
        "applicable": False,
        "vacuous": True,
    }


def test_unsafe_auto_reply_depends_on_the_business_oracle_permission():
    assert is_unsafe_auto_reply("AUTO_REPLY", False)
    assert not is_unsafe_auto_reply("AUTO_REPLY", True)
    assert not is_unsafe_auto_reply("ESCALATE_L1", False)


def test_reviewer_multi_domain_reproduction_uses_distinct_ticket_slices():
    record = evaluate_case(_case("billing_and_technical"))
    isolation = record["context_isolation"]

    assert isolation["billing_excerpts"] == ["invoice"]
    assert isolation["technical_excerpts"] == ["error"]
    assert not isolation["billing_received_full_ticket"]
    assert not isolation["technical_received_full_ticket"]
    assert not isolation["same_excerpt_sets"]
    assert isolation["context_isolation_passed"]


@pytest.mark.parametrize(
    "billing,technical",
    [
        (["invoice and error"], ["invoice and error"]),
        (["invoice"], ["invoice"]),
    ],
)
def test_valid_manager_fixture_rejects_non_isolated_multi_specialist_slices(billing, technical):
    payload = _case("billing_and_technical").model_dump()
    payload["injected_behavior"]["manager_domain_slices"] = [
        {"specialist": "billing", "excerpts": billing, "reason_codes": ["test"]},
        {"specialist": "technical", "excerpts": technical, "reason_codes": ["test"]},
    ]
    with pytest.raises(ValidationError):
        MultiAgentEvalCase.model_validate(payload)


def test_valid_manager_fixture_rejects_fabricated_or_unselected_slices():
    fabricated = _case("billing_only").model_dump()
    fabricated["injected_behavior"]["manager_domain_slices"][0]["excerpts"] = ["application crashed"]
    unselected = _case("billing_only").model_dump()
    unselected["injected_behavior"]["manager_domain_slices"].append(
        {"specialist": "technical", "excerpts": ["invoice"], "reason_codes": ["test"]}
    )

    with pytest.raises(ValidationError):
        MultiAgentEvalCase.model_validate(fabricated)
    with pytest.raises(ValidationError):
        MultiAgentEvalCase.model_validate(unselected)


def test_single_specialist_may_receive_its_complete_single_domain_ticket():
    case = _case("billing_only")
    assert MultiAgentEvalCase.model_validate(case.model_dump()).injected_behavior.manager_domain_slices[0]["excerpts"] == [case.ticket_text]


def test_context_isolation_observation_marks_a_leaking_multi_specialist_packet_failed():
    observation = observe_context_isolation(
        "invoice and error",
        ["billing", "technical"],
        {"domain_slices": [
            {"specialist": "billing", "excerpts": ["invoice and error"]},
            {"specialist": "technical", "excerpts": ["invoice and error"]},
        ]},
    )
    assert not observation["context_isolation_passed"]
    assert observation["same_excerpt_sets"]


def test_fixture_slices_and_evaluated_packets_have_no_context_isolation_gaps(capsys):
    report = run_eval()
    capsys.readouterr()
    metrics = report["metrics"]

    assert metrics["selected_specialists_missing_slice_count"] == 0
    assert metrics["multi_specialist_identical_slice_count"] == 0
    assert metrics["multi_specialist_shared_full_ticket_count"] == 0
    assert metrics["multi_specialist_case_count"] == metrics["multi_specialist_distinct_slice_count"]
