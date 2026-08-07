"""A4: HITL checkpoint — approval/execution separation + approved content binding + resume.

Invariants:
- approve does NOT execute (adapter 0); the mock action happens on explicit resume.
- what was approved (SHA-256 bound) is what may be executed; tamper/stale is blocked.
- resume revalidates state, integrity, evidence and idempotency.
- checkpoint survives a new service/repository instance on the same SQLite file.
"""
import pytest

from service.action_adapter import MockTicketActionAdapter
from service.domain import (
    ActionStatus,
    Decision,
    ReviewRequest,
    ReviewStatus,
    ReviewerAction,
    TicketCreate,
)
from service.engine import NoEvidenceGate, TicketWorkflowService
from service.repository import InvalidTransition, TicketRepository

from tests._service_helpers import make_fake_decision_fn


def _svc(db_path, **kw):
    return TicketWorkflowService(enable_ledger=False, db_path=str(db_path), **kw)


def _create(svc, tid="T-A4-001"):
    svc.create_ticket(TicketCreate(ticket_text="How do I reset my password?", ticket_id=tid))


def _approve(svc, tid="T-A4-001", action=ReviewerAction.APPROVED, edited=None):
    return svc.review_ticket(tid, ReviewRequest(reviewer_action=action, edited_draft=edited))


def test_pause_creates_waiting_checkpoint_no_adapter(tmp_path):
    db = tmp_path / "t.db"
    svc = _svc(db, decision_fn=make_fake_decision_fn())
    _create(svc)
    rec = svc.get_ticket("T-A4-001")
    assert rec.action_status == ActionStatus.PENDING.value  # waiting for review
    assert rec.approved_payload_hash is None
    assert len(svc.list_actions("T-A4-001")) == 0


def test_approve_binds_payload_and_ready_for_execution(tmp_path):
    db = tmp_path / "t.db"
    svc = _svc(db, decision_fn=make_fake_decision_fn(draft="Agent draft A"))
    _create(svc)
    out = _approve(svc)
    assert out.action is None  # approval does not execute
    rec = svc.get_ticket("T-A4-001")
    assert rec.review_status == ReviewStatus.APPROVED
    assert rec.action_status == ActionStatus.READY_FOR_EXECUTION.value
    assert rec.approved_payload == "Agent draft A"
    assert rec.approved_payload_hash == TicketWorkflowService._payload_hash("Agent draft A")
    assert rec.review_version == 1
    assert len(svc.list_actions("T-A4-001")) == 0


def test_reject_then_resume_blocked(tmp_path):
    db = tmp_path / "t.db"
    svc = _svc(db, decision_fn=make_fake_decision_fn())
    _create(svc)
    svc.review_ticket("T-A4-001", ReviewRequest(reviewer_action=ReviewerAction.REJECTED))
    with pytest.raises(InvalidTransition) as e:
        svc.execute_approved_reply("T-A4-001")
    assert "rejected" in str(e.value)


def test_edit_approve_executes_edited_payload(tmp_path):
    db = tmp_path / "t.db"
    recorder = []
    adapter = MockTicketActionAdapter(recorder=lambda ev: recorder.append(ev))
    svc = _svc(db, decision_fn=make_fake_decision_fn(draft="Agent draft A"), adapter=adapter)
    _create(svc)
    _approve(svc, action=ReviewerAction.EDITED, edited="Human edited B")
    rec = svc.get_ticket("T-A4-001")
    assert rec.approved_payload == "Human edited B"
    assert rec.approved_payload_hash == TicketWorkflowService._payload_hash("Human edited B")
    svc.execute_approved_reply("T-A4-001")
    assert recorder and recorder[0]["draft_preview"] == "Human edited B"


def test_tamper_after_approval_blocks_execute(tmp_path):
    # Integrity defense test: controlled repository fault injection mutates the
    # approved payload after approval. Resume must refuse (stale_approved_draft).
    db = tmp_path / "t.db"
    svc = _svc(db, decision_fn=make_fake_decision_fn(draft="Approved A"))
    _create(svc)
    _approve(svc)
    repo = TicketRepository(str(db))
    t = repo.get_ticket("T-A4-001")
    t.approved_payload = "Tampered B"
    repo.update_ticket(t)
    repo.close()
    with pytest.raises(InvalidTransition) as e:
        svc.execute_approved_reply("T-A4-001")
    assert "stale_approved_draft" in str(e.value)


def test_restart_resume_executes_approved_content(tmp_path):
    # Minimal checkpoint/resume proof: a new service + repository instance on
    # the same SQLite file reads the persisted checkpoint and executes the
    # approved content exactly once.
    db = tmp_path / "t.db"
    svc_a = _svc(db, decision_fn=make_fake_decision_fn(draft="Approved content"))
    _create(svc_a)
    _approve(svc_a)
    assert svc_a.get_ticket("T-A4-001").action_status == ActionStatus.READY_FOR_EXECUTION.value

    svc_b = _svc(db, decision_fn=make_fake_decision_fn())
    out = svc_b.execute_approved_reply("T-A4-001")
    assert out.action is not None
    assert out.action.status == ActionStatus.EXECUTED
    assert "sent_mock" in (out.action.result or {}).get("status", "")


def test_unsafe_grounding_blocks_execute_even_after_approval(tmp_path):
    db = tmp_path / "t.db"
    svc = _svc(db, decision_fn=make_fake_decision_fn(grounding_safe=False))
    _create(svc)
    _approve(svc)
    with pytest.raises(NoEvidenceGate):
        svc.execute_approved_reply("T-A4-001")


def test_duplicate_execute_is_idempotent(tmp_path):
    db = tmp_path / "t.db"
    svc = _svc(db, decision_fn=make_fake_decision_fn())
    _create(svc)
    _approve(svc)
    r1 = svc.execute_approved_reply("T-A4-001")
    r2 = svc.execute_approved_reply("T-A4-001")
    assert r1.action.status == ActionStatus.EXECUTED
    assert "already executed" in r2.message
    assert len(svc.list_actions("T-A4-001")) == 1


def test_failed_then_previous_execution_failed(tmp_path):
    db = tmp_path / "t.db"

    class BoomAdapter(MockTicketActionAdapter):
        def create_reply(self, **kw):
            raise RuntimeError("boom")

    svc = _svc(db, decision_fn=make_fake_decision_fn(), adapter=BoomAdapter())
    _create(svc)
    _approve(svc)
    with pytest.raises(RuntimeError):
        svc.execute_approved_reply("T-A4-001")
    with pytest.raises(InvalidTransition) as e:
        svc.execute_approved_reply("T-A4-001")
    assert "previous_execution_failed" in str(e.value)


def test_review_version_increments_per_approval_bound(tmp_path):
    db = tmp_path / "t.db"
    svc = _svc(db, decision_fn=make_fake_decision_fn())
    _create(svc)
    _approve(svc)
    rec = svc.get_ticket("T-A4-001")
    assert rec.review_version == 1
    # the approved payload + hash are the checkpoint's integrity root
    assert rec.approved_payload_hash == TicketWorkflowService._payload_hash(rec.approved_payload)
