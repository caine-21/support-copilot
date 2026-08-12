from __future__ import annotations

import io
import logging

from fastapi.testclient import TestClient

from scripts.failure_recovery import run_exercise
from service.config import RuntimeSettings
from service.engine import TicketWorkflowService
from service.observability import Telemetry
from service.operable import create_operable_app
from tests._service_helpers import make_fake_decision_fn


def _settings(**overrides: str) -> RuntimeSettings:
    return RuntimeSettings.from_env({
        "SUPPORT_DEPLOYMENT_MODE": "local",
        "SUPPORT_ALLOWED_HOSTS": "testserver,localhost",
        "ENABLE_CUSTOMER_PORTAL": "true",
        **overrides,
    })


def _client(tmp_path, telemetry=None):
    service = TicketWorkflowService(
        db_path=str(tmp_path / "tickets.db"),
        decision_fn=make_fake_decision_fn(),
        enable_ledger=False,
        telemetry=telemetry,
    )
    cfg = _settings(ENABLE_PROVIDER_CALLS="false", ENABLE_EXECUTOR="false")
    return TestClient(create_operable_app(settings=cfg, service=service, telemetry=telemetry))


def test_validation_error_is_structured_and_traceable(tmp_path):
    client = _client(tmp_path)
    response = client.post("/customer/tickets", json={})
    body = response.json()
    assert response.status_code == 422
    assert body["errorType"] == "validation"
    assert body["error"] == "request validation failed"
    assert body["requestId"] == response.headers["x-request-id"]
    assert "input" not in body


def test_http_error_is_structured_and_traceable(tmp_path):
    client = _client(tmp_path)
    response = client.get("/not-a-real-route")
    body = response.json()
    assert response.status_code == 404
    assert body["errorType"] == "not_found"
    assert body["requestId"] == response.headers["x-request-id"]


def test_request_completed_log_has_http_identity_and_no_ticket_text(tmp_path):
    stream = io.StringIO()
    logger = logging.getLogger("support_copilot.productionization.test")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler(stream))
    logger.propagate = False
    telemetry = Telemetry(_settings(), logger=logger)
    client = _client(tmp_path, telemetry)

    response = client.post(
        "/customer/tickets",
        headers={"X-Request-ID": "prod-log-test"},
        json={"ticket_text": "reset password"},
    )
    assert response.status_code == 201
    records = [line for line in stream.getvalue().splitlines() if '"event":"request_completed"' in line]
    assert records
    record = __import__("json").loads(records[-1])
    assert record["request_id"] == "prod-log-test"
    assert record["method"] == "POST"
    assert record["path"] == "/customer/tickets"
    assert record["status_code"] == 201
    assert isinstance(record["latency_ms"], (int, float))
    assert "reset password" not in stream.getvalue()


def test_render_commit_fills_release_identity_when_build_arg_is_unknown():
    cfg = RuntimeSettings.from_env({
        "SUPPORT_DEPLOYMENT_MODE": "staging",
        "SUPPORT_API_TOKEN": "test-token",
        "SUPPORT_GIT_SHA": "unknown",
        "RENDER_GIT_COMMIT": "cfe3ce8f8488d2c2f42a7228680d7dbb60c2a550",
    })
    assert cfg.git_sha == "cfe3ce8f8488d2c2f42a7228680d7dbb60c2a550"


def test_failure_exercise_classifies_and_recovers():
    result = run_exercise()
    assert result["observed"]["classified_error"] == "provider_timeout"
    assert result["observed"]["failed_workflow_status"] == "failed"
    assert result["observed"]["failed_decision"] == "UNKNOWN"
    assert result["recovery"] == {
        "workflow_status": "completed",
        "decision": "AUTO_REPLY",
        "grounding_safe": True,
    }
    assert result["secret_leakage"] is False
