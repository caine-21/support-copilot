from agent.multi_agent.specialists import run_specialist


def test_specialist_validates_and_safe_fails():
    ok = run_specialist("billing", {}, lambda n, c: {"applicable": True, "confidence": .8, "recommended_route": "escalate_l1"})
    bad = run_specialist("technical", {}, lambda n, c: "not json")
    assert ok.error is None and ok.specialist == "billing"
    assert bad.error and bad.applicable is False and bad.risk_flags == ["specialist_failure"]
