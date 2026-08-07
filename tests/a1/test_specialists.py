"""Specialist lanes: independent contracts, read-only, fail-closed."""
from unittest import mock

from app.specialists.contracts import (
    KnowledgeSpecialistInput,
    SpecialistStatus,
    SupportSpecialistInput,
)
from app.specialists.knowledge_specialist import run_knowledge_specialist
from app.specialists.support_specialist import run_support_specialist


def test_knowledge_known_intent_returns_faq_evidence():
    k = run_knowledge_specialist(KnowledgeSpecialistInput(
        request_id="r", query="How do I download my invoice?", intent="invoice_download", top_k=3))
    assert k.status is SpecialistStatus.SUCCESS
    assert k.evidence
    assert any(e["doc_id"] == "FAQ-billing-01" for e in k.evidence)
    # A specialist never carries authorization.
    assert not hasattr(k, "authorization")


def test_knowledge_error_fails_closed():
    with mock.patch("app.specialists.knowledge_specialist._kb_search",
                    side_effect=RuntimeError("boom")):
        k = run_knowledge_specialist(KnowledgeSpecialistInput(
            request_id="r", query="q", intent="x", top_k=3))
    assert k.status is SpecialistStatus.ERROR
    assert k.evidence == []
    assert not hasattr(k, "authorization")


def test_support_proposal_grounded_from_evidence():
    evidence = [{"doc_id": "FAQ-billing-01", "snippet": "Go to Settings Billing Invoice History.", "score": 1.0}]
    s = run_support_specialist(SupportSpecialistInput(
        request_id="r", text="how do I invoice?", intents=["invoice_download"], evidence=evidence))
    assert s.status is SpecialistStatus.SUCCESS
    assert s.proposal["grounded"] is True
    assert "Settings" in s.proposal["draft"]
    assert s.evidence_refs == ["FAQ-billing-01"]
    assert not hasattr(s, "authorization")


def test_support_no_evidence_no_proposal():
    s = run_support_specialist(SupportSpecialistInput(
        request_id="r", text="x", intents=[], evidence=[]))
    assert s.status is SpecialistStatus.NO_EVIDENCE
    assert s.proposal["draft"] == ""
    assert s.confidence < 0.5
