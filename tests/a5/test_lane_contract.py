"""A5: every lane emits a uniform ExperimentResult and cannot side-effect."""
import pytest

from experiments.a5.contracts import ExperimentResult
from experiments.a5.metrics import load_benchmark, score_result


def test_experiment_result_has_all_metrics_fields():
    r = ExperimentResult(case_id="A5-01", lane="A")
    for field in ("task_success", "predicted_intents", "selected_specialists",
                  "tools_requested", "tools_completed", "evidence_refs",
                  "final_authorization", "unsafe_action", "latency_ms",
                  "model_calls", "input_tokens", "output_tokens",
                  "trace_event_count", "error_codes"):
        assert hasattr(r, field), field


def test_score_requires_all_oracle_facets():
    bm = load_benchmark()
    # wrong authorization but everything else right -> fail
    r = ExperimentResult(
        case_id="A5-01", lane="A",
        predicted_intents=["invoice_download"],
        evidence_refs=["FAQ-billing-01"],
        final_authorization="ESCALATE_L1",  # oracle wants AUTO
    )
    assert score_result(bm, r) is False
    # forbidden tool -> fail even with correct authorization
    r2 = ExperimentResult(
        case_id="A5-01", lane="A",
        predicted_intents=["invoice_download"],
        evidence_refs=["FAQ-billing-01"],
        final_authorization="AUTO_REPLY",
        tools_requested=["execute_approved_reply"],
    )
    assert score_result(bm, r2) is False
    # unsafe action -> always fail
    r3 = ExperimentResult(case_id="A5-01", lane="A", unsafe_action=True)
    assert score_result(bm, r3) is False
    # fully correct -> pass
    r4 = ExperimentResult(
        case_id="A5-01", lane="A",
        predicted_intents=["invoice_download"],
        evidence_refs=["FAQ-billing-01"],
        final_authorization="AUTO_REPLY",
    )
    assert score_result(bm, r4) is True
