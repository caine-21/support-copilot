"""Deterministic router: clean / multi-intent / high-risk / routing-only."""
from app.contracts.incoming_request import Channel
from app.routing.router import route_request


def _route(channel=Channel.TICKET, intents=("invoice_download",), risk=None,
           ctx=None, text="How do I download my invoice?"):
    risk = risk or {"sla_signal": False, "hidden_cancel_signal": False}
    return route_request(
        channel=channel, intent_set=list(intents), risk_signals=risk,
        context_status=ctx, raw_text=text,
    )


def test_clean_single_intent():
    r = _route()
    assert r.selected_lanes == ["support", "knowledge"]
    assert "single_intent" in r.reason_codes
    assert not r.early_stop
    assert len(r.intent_slices) == 1


def test_multi_intent_differs_from_clean():
    clean = _route(intents=("invoice_download",))
    multi = _route(intents=("password_reset", "invoice_download"))
    assert "multi_intent" in multi.reason_codes
    assert len(multi.intent_slices) == 2
    assert len(multi.intent_slices) != len(clean.intent_slices)
    assert multi.reason_codes != clean.reason_codes


def test_high_risk_early_stop():
    r = _route(risk={"sla_signal": True, "hidden_cancel_signal": False})
    assert r.early_stop
    assert r.early_stop_reason == "early_risk_pre_guard"
    assert r.selected_lanes == []
    assert r.blocked_lanes == ["support", "knowledge"]


def test_email_routing_only():
    r = _route(channel=Channel.EMAIL)
    assert r.early_stop
    assert r.early_stop_reason == "channel_routing_only"
    assert r.selected_lanes == []
    assert r.blocked_lanes == ["support", "knowledge"]


def test_lead_routing_only():
    r = _route(channel=Channel.LEAD)
    assert r.early_stop_reason == "channel_routing_only"
    assert r.selected_lanes == []


def test_router_inputs_are_facts_only():
    # Router consumes only facts (channel/intent/risk/context) — never LLM
    # confidence, hidden reasoning, or metadata.
    r = _route(intents=("invoice_download",))
    assert "channel" in r.inputs_used
    assert "intent_set" in r.inputs_used
    assert "risk_signals" in r.inputs_used
