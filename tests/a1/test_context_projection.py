"""Context projection: specialists see only their minimal, read-only view."""
from app.contracts.incoming_request import Channel, ChannelCapability, IncomingRequest
from app.runtime.context_projection import project_for_knowledge, project_for_support
from app.runtime.state import SharedRuntimeState


def _state(secret_ctx=None, meta=None):
    req = IncomingRequest(
        request_id="r-secret",
        channel=Channel.TICKET,
        raw_text="I cannot log in and my invoice is missing",
        sender_context=secret_ctx,
        metadata=meta or {"route": "AUTO_REPLY", "agent": "executor", "tool": "send_reply"},
    )
    return SharedRuntimeState(request=req, capability_status=ChannelCapability.SUPPORTED)


def test_knowledge_projection_minimal_and_clean():
    st = _state(secret_ctx={"plan": "team", "email": "secret@corp.com", "phone": "+86 138 0000 0000"})
    k = project_for_knowledge(st, {"intent": "password_reset", "query": st.request.raw_text})
    d = k.model_dump()
    assert set(d.keys()) == {"request_id", "query", "intent", "top_k"}
    # No PII / sender context / metadata leak into the knowledge view.
    assert "email" not in str(d)
    assert "phone" not in str(d)
    assert "plan" not in str(d)
    assert "send_reply" not in str(d)


def test_support_projection_allowlist_only():
    st = _state(secret_ctx={
        "plan": "team", "region": "eu", "role": "admin",
        "email": "secret@corp.com", "account_status": "active",
    })
    s = project_for_support(st, {"intent": "password_reset", "query": st.request.raw_text}, [])
    # Only the allowlisted sender fields are projected.
    assert s.sender_context == {"plan": "team", "region": "eu", "role": "admin"}
    assert "email" not in str(s.sender_context)
    assert "account_status" not in str(s.sender_context)


def test_projection_never_exposes_runtime_internals():
    st = _state()
    k = project_for_knowledge(st, {"intent": "x", "query": "q"})
    s = project_for_support(st, {"intent": "x", "query": "q"}, [])
    for blob in (k.model_dump(), s.model_dump()):
        for forbidden in ("authorization", "lane_results", "route_decision",
                          "grounding_status", "risk_signals", "capability_status"):
            assert forbidden not in str(blob)
    joined = str(k.model_dump()) + str(s.model_dump())
    for forbidden in ("send_reply", "executor", "idempotency",
                      "mock_action", "MockTicketActionAdapter", "review_decision"):
        assert forbidden not in joined
