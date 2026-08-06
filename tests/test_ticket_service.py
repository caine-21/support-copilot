"""Engine-level tests for the ticket workflow slice — fully offline (fake decision port)."""
from __future__ import annotations

import pytest

from service.action_adapter import MockTicketActionAdapter
from service.domain import (
    ActionStatus,
    Decision,
    ReviewRequest,
    ReviewStatus,
    ReviewerAction,
    TicketCreate,
    WorkflowStatus,
)
from service.engine import TicketWorkflowService
from service.repository import InvalidTransition, NoEvidenceGate, TicketRepository

from _service_helpers import make_fake_decision_fn


@pytest.fixture
def repo(tmp_path):
    return TicketRepository(str(tmp_path / "tickets.db"))


@pytest.fixture
def svc_factory(repo):
    def _make(**kw):
        return TicketWorkflowService(repo=repo, enable_ledger=False, **kw)

    return _make


def _auto_ticket(svc, **kw) -> None:
    svc.create_ticket(TicketCreate(ticket_text="How do I reset my password?", **kw))


def test_create_ticket_persists_decision(repo, svc_factory):
    svc = svc_factory(decision_fn=make_fake_decision_fn())
    rec = svc.create_ticket(TicketCreate(ticket_text="How do I reset my password?", ticket_id="T-1"))
    assert rec.workflow_status == WorkflowStatus.COMPLETED
    assert rec.decision == Decision.AUTO_REPLY.value
    assert rec.review_status == ReviewStatus.PENDING
    assert rec.action_status == ActionStatus.PENDING.value
    assert rec.draft_response.startswith("Thanks")
    assert rec.retrieved_evidence[0]["doc_id"] == "FAQ-password-reset"
    assert rec.grounding_safe is True
    assert rec.idempotency_key == "T-1:1:create_reply"

    # survives reopen (persistence)
    repo2 = TicketRepository(repo.db_path)
    rec2 = repo2.get_ticket("T-1")
    assert rec2.decision == Decision.AUTO_REPLY.value
    assert rec2.draft_response == rec.draft_response
    repo2.close()


def test_duplicate_create_rejected(repo, svc_factory):
    svc = svc_factory(decision_fn=make_fake_decision_fn())
    _auto_ticket(svc, ticket_id="T-dup")
    with pytest.raises(InvalidTransition):
        _auto_ticket(svc, ticket_id="T-dup")


def test_query_ticket(repo, svc_factory):
    svc = svc_factory(decision_fn=make_fake_decision_fn())
    _auto_ticket(svc, ticket_id="T-q")
    rec = svc.get_ticket("T-q")
    assert rec.ticket_id == "T-q"
    assert rec.review_status == ReviewStatus.PENDING


def test_decision_flow_failure_is_recorded_not_success(repo, svc_factory):
    svc = svc_factory(
        decision_fn=make_fake_decision_fn(raise_error=RuntimeError("provider down"))
    )
    rec = svc.create_ticket(TicketCreate(ticket_text="anything", ticket_id="T-fail"))
    assert rec.workflow_status == WorkflowStatus.FAILED
    assert rec.decision == Decision.UNKNOWN.value
    assert "provider down" in (rec.decision_reason or "")


def test_approve_executes_action_once(repo, svc_factory):
    svc = svc_factory(decision_fn=make_fake_decision_fn())
    _auto_ticket(svc, ticket_id="T-a")
    out = svc.review_ticket(
        "T-a",
        ReviewRequest(reviewer_action=ReviewerAction.APPROVED, reason_code="safe_to_send"),
    )
    assert out.action is not None
    assert out.action.status == ActionStatus.EXECUTED
    assert out.action.action_type == "create_reply"
    assert out.ticket.review_status == ReviewStatus.APPROVED
    assert out.ticket.action_status == ActionStatus.EXECUTED.value
    assert len(svc.list_actions("T-a")) == 1


def test_repeat_approve_does_not_re_execute(repo, svc_factory):
    svc = svc_factory(decision_fn=make_fake_decision_fn())
    _auto_ticket(svc, ticket_id="T-idem")
    first = svc.review_ticket("T-idem", ReviewRequest(reviewer_action=ReviewerAction.APPROVED))
    assert first.action.status == ActionStatus.EXECUTED
    second = svc.review_ticket("T-idem", ReviewRequest(reviewer_action=ReviewerAction.APPROVED))
    assert second.action is not None
    assert second.action.id == first.action.id  # same row, not re-executed
    assert second.action.status == ActionStatus.EXECUTED
    assert "no re-execution" in second.message
    assert len(svc.list_actions("T-idem")) == 1  # only one action row ever


def test_review_rejected_takes_no_action(repo, svc_factory):
    svc = svc_factory(decision_fn=make_fake_decision_fn())
    _auto_ticket(svc, ticket_id="T-rej")
    out = svc.review_ticket(
        "T-rej",
        ReviewRequest(reviewer_action=ReviewerAction.REJECTED, reason_code="content_risk_too_high"),
    )
    assert out.ticket.review_status == ReviewStatus.REJECTED
    assert out.action is None
    assert len(svc.list_actions("T-rej")) == 0


def test_unsafe_auto_reply_blocked_by_evidence_gate(repo, svc_factory):
    svc = svc_factory(
        decision_fn=make_fake_decision_fn(action="AUTO_REPLY", grounding_safe=False)
    )
    _auto_ticket(svc, ticket_id="T-unsafe")
    with pytest.raises(NoEvidenceGate):
        svc.review_ticket("T-unsafe", ReviewRequest(reviewer_action=ReviewerAction.APPROVED))
    # nothing executed, ticket still pending
    assert len(svc.list_actions("T-unsafe")) == 0
    rec = svc.get_ticket("T-unsafe")
    assert rec.review_status == ReviewStatus.PENDING


def test_adapter_failure_recorded_not_success(repo, svc_factory):
    class BoomAdapter(MockTicketActionAdapter):
        def create_reply(self, *, ticket_id, draft, evidence):
            raise RuntimeError("mock send failed")

    svc = svc_factory(decision_fn=make_fake_decision_fn(), adapter=BoomAdapter())
    _auto_ticket(svc, ticket_id="T-err")
    with pytest.raises(RuntimeError):
        svc.review_ticket("T-err", ReviewRequest(reviewer_action=ReviewerAction.APPROVED))
    actions = svc.list_actions("T-err")
    assert len(actions) == 1
    assert actions[0].status == ActionStatus.FAILED
    assert "mock send failed" in (actions[0].error or "")
    rec = svc.get_ticket("T-err")
    assert rec.action_status == ActionStatus.FAILED.value  # not marked success
    assert rec.workflow_status == WorkflowStatus.COMPLETED  # decision itself was fine


def test_escalation_path_uses_create_escalation(repo, svc_factory):
    svc = svc_factory(
        decision_fn=make_fake_decision_fn(action="ESCALATE_L2", grounding_safe=None)
    )
    _auto_ticket(svc, ticket_id="T-l2")
    out = svc.review_ticket("T-l2", ReviewRequest(reviewer_action=ReviewerAction.APPROVED))
    assert out.action.action_type == "create_escalation"
    assert out.action.status == ActionStatus.EXECUTED
    assert "escalated_mock" in (out.action.result or {}).get("status", "")


def test_cannot_review_failed_workflow(repo, svc_factory):
    svc = svc_factory(decision_fn=make_fake_decision_fn(raise_error=RuntimeError("boom")))
    rec = svc.create_ticket(TicketCreate(ticket_text="x", ticket_id="T-norev"))
    assert rec.workflow_status == WorkflowStatus.FAILED
    with pytest.raises(InvalidTransition):
        svc.review_ticket("T-norev", ReviewRequest(reviewer_action=ReviewerAction.APPROVED))
