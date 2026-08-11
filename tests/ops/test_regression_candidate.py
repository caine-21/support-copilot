from scripts.capture_regression_candidate import build_candidate


def test_candidate_is_sanitized_and_review_gated():
    candidate = build_candidate({
        "failure": "contact alice@example.com password=hunter2",
        "authorization": "Bearer secret-token",
        "expected": "one execution",
    })
    rendered = str(candidate)
    assert "alice@example.com" not in rendered
    assert "hunter2" not in rendered
    assert "secret-token" not in rendered
    assert candidate["review_status"] == "pending_human_review"
