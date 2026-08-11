from ops.challenge import run_matrix


def test_all_failure_matrix_cases_pass():
    result = run_matrix()
    assert result["summary"] == {"total": 17, "passed": 17, "failed": 0}
    assert result["external_side_effects"] == 0
