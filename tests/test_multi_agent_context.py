from agent.multi_agent.context import build_billing_context, build_manager_context, build_technical_context, fallback_slices, validate_slices
from agent.multi_agent.contracts import DomainTicketSlice
from agent.multi_agent.manager import decide_manager

KB = [{"doc_id": "FAQ-billing-01", "snippet": "invoice payment", "score": 1}, {"doc_id": "FAQ-troubleshoot-01", "snippet": "login error", "score": 1}]
CTX = {"fields": {name: {"value": "secret", "status": "known", "source": "fixture"} for name in ("plan", "region", "role", "permissions", "contract_status", "account_status")}}


def test_context_isolation_and_kb_partitioning():
    billing = build_billing_context("invoice", {"intent": "billing"}, KB, CTX)
    technical = build_technical_context("error", {"intent": "bug"}, KB, {"past_tickets": [{"intent": "bug", "raw": "do not share"}]})
    manager = build_manager_context("x", {"intent": "billing"}, {"tone": "neutral"}, KB)
    assert [x["doc_id"] for x in billing["kb"]] == ["FAQ-billing-01"]
    assert [x["doc_id"] for x in technical["kb"]] == ["FAQ-troubleshoot-01"]
    assert "contract_status" not in technical and "fields" not in billing
    assert set(manager) == {"ticket_text", "classification", "intent_set", "tone_summary", "kb"}
    assert "secret" not in str(technical) and ".env" not in str(manager)


def test_fallback_slices_keep_multi_domain_ticket_contexts_distinct():
    ticket = "invoice and error"
    slices = [DomainTicketSlice.model_validate(row) for row in fallback_slices(ticket, ["billing", "technical"])]
    accepted, errors = validate_slices(ticket, ["billing", "technical"], slices)

    assert errors == []
    assert {row["specialist"]: row["excerpts"] for row in accepted} == {
        "billing": ["invoice"],
        "technical": ["error"],
    }


def test_context_validation_rejects_identical_multi_specialist_slices():
    ticket = "invoice and error"
    slices = [
        DomainTicketSlice(specialist="billing", excerpts=[ticket]),
        DomainTicketSlice(specialist="technical", excerpts=[ticket]),
    ]
    accepted, errors = validate_slices(ticket, ["billing", "technical"], slices)

    assert accepted == []
    assert "domain_slice_not_isolated" in errors
    assert "domain_slice_full_ticket_shared" in errors


def test_invalid_manager_fallback_keeps_multi_domain_slices_distinct():
    decision, errors = decide_manager(
        build_manager_context("invoice and error", {"intent": "billing", "secondary_intent": "bug"}, {}, []),
        runner=lambda _: "{invalid-json",
    )

    assert [error.code for error in errors] == ["manager_json_invalid"]
    assert {item.specialist: item.excerpts for item in decision.domain_slices} == {
        "billing": ["invoice"],
        "technical": ["error"],
    }
