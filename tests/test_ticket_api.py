"""API-level tests for the ticket workflow slice (FastAPI TestClient, offline)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service.api import create_app
from service.engine import TicketWorkflowService
from service.repository import TicketRepository

from _service_helpers import make_fake_decision_fn


@pytest.fixture
def client(tmp_path):
    repo = TicketRepository(str(tmp_path / "tickets.db"))
    svc = TicketWorkflowService(repo=repo, decision_fn=make_fake_decision_fn(), enable_ledger=False)
    return TestClient(create_app(service=svc))


def test_create_and_query_ticket(client):
    r = client.post(
        "/tickets",
        json={"ticket_text": "How do I reset my password?", "ticket_id": "T-api-1"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["decision"] == "AUTO_REPLY"
    assert body["workflow_status"] == "completed"
    assert body["review_status"] == "pending_review"

    g = client.get("/tickets/T-api-1")
    assert g.status_code == 200
    assert g.json()["ticket_id"] == "T-api-1"


def test_get_missing_ticket_404(client):
    r = client.get("/tickets/nope")
    assert r.status_code == 404


def test_duplicate_create_conflict(client):
    payload = {"ticket_text": "hi", "ticket_id": "T-dup-api"}
    assert client.post("/tickets", json=payload).status_code == 201
    r = client.post("/tickets", json=payload)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_review_approve_creates_checkpoint_not_executes(client):
    client.post("/tickets", json={"ticket_text": "hi", "ticket_id": "T-rv"})
    r = client.post("/tickets/T-rv/review", json={"reviewer_action": "approved", "reviewer_id": "me"})
    assert r.status_code == 200
    body = r.json()
    assert body["action"] is None  # approval does not execute
    assert body["ticket"]["review_status"] == "approved"
    assert body["ticket"]["action_status"] == "ready_for_execution"
    assert body["ticket"]["approved_payload_hash"] is not None

    # second review → idempotent "already reviewed", no execution
    r2 = client.post("/tickets/T-rv/review", json={"reviewer_action": "approved", "reviewer_id": "me"})
    assert r2.status_code == 200
    assert "already reviewed" in r2.json()["message"]

    # no action rows — execution is a separate executor step
    acts = client.get("/tickets/T-rv/actions")
    assert acts.status_code == 200
    assert len(acts.json()) == 0


def test_review_rejected_no_action(client):
    client.post("/tickets", json={"ticket_text": "hi", "ticket_id": "T-rej-api"})
    r = client.post(
        "/tickets/T-rej-api/review",
        json={"reviewer_action": "rejected", "reviewer_id": "me", "reason_code": "content_risk_too_high"},
    )
    assert r.status_code == 200
    assert r.json()["action"] is None
    assert r.json()["ticket"]["review_status"] == "rejected"
    assert len(client.get("/tickets/T-rej-api/actions").json()) == 0


def test_unsafe_auto_reply_approval_ok_execution_gated(client):
    # A4: approval creates a checkpoint even when grounding is unsafe; the
    # NoEvidenceGate is enforced at EXECUTION time (executor-only), so the
    # review endpoint returns 200 with READY_FOR_EXECUTION.
    repo = TicketRepository(":memory:")
    svc = TicketWorkflowService(
        repo=repo,
        decision_fn=make_fake_decision_fn(action="AUTO_REPLY", grounding_safe=False),
        enable_ledger=False,
    )
    c = TestClient(create_app(service=svc))
    c.post("/tickets", json={"ticket_text": "unsafe", "ticket_id": "T-unsafe-api"})
    r = c.post("/tickets/T-unsafe-api/review", json={"reviewer_action": "approved"})
    assert r.status_code == 200
    assert r.json()["ticket"]["action_status"] == "ready_for_execution"
    assert r.json()["ticket"]["approved_payload_hash"] is not None


def test_review_missing_ticket_404(client):
    r = client.post("/tickets/missing/review", json={"reviewer_action": "approved"})
    assert r.status_code == 404


def test_review_edited_uses_edited_draft(client):
    client.post("/tickets", json={"ticket_text": "hi", "ticket_id": "T-edit"})
    r = client.post(
        "/tickets/T-edit/review",
        json={"reviewer_action": "edited", "reviewer_id": "me", "edited_draft": "Edited reply text"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ticket"]["review_status"] == "edited"
    assert body["ticket"]["approved_payload"] == "Edited reply text"
    assert body["ticket"]["approved_payload_hash"] is not None
