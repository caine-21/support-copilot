from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from agent.llm import LLMRouter, classify_provider_error, set_provider_observer
from service.action_adapter import MockTicketActionAdapter
from service.domain import ReviewRequest, ReviewerAction, TicketCreate
from service.engine import InvalidTransition, TicketWorkflowService
from tests._service_helpers import make_fake_decision_fn


class ProviderError(Exception):
    def __init__(self, status_code: int):
        super().__init__("provider failure")
        self.status_code = status_code


class FakeClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **_kwargs):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.outcome))]
        )


def router_with(primary, fallback):
    router = LLMRouter()
    first = FakeClient(primary)
    second = FakeClient(fallback)
    router._deepseek = lambda: first
    router._groq = lambda: second
    return router, first, second


@pytest.mark.parametrize(
    ("error", "expected"),
    [(TimeoutError(), "timeout"), (ProviderError(429), "rate_limit"), (ProviderError(503), "server_error")],
)
def test_provider_error_taxonomy(error, expected):
    assert classify_provider_error(error)[0] == expected


def test_timeout_and_rate_limit_fallback_once_without_retry_storm():
    for failure in (TimeoutError(), ProviderError(429)):
        events = []
        set_provider_observer(lambda event, fields: events.append((event, fields)))
        router, primary, fallback = router_with(failure, '{"ok":true}')
        assert router.call([{"role": "user", "content": "synthetic"}]) == '{"ok":true}'
        assert primary.calls == 1
        assert fallback.calls == 1
        assert len([event for event, _ in events if event == "provider_fallback"]) == 1
    set_provider_observer(None)


def test_malformed_or_both_unavailable_has_explicit_failure():
    router, primary, fallback = router_with(TypeError("malformed"), ProviderError(503))
    with pytest.raises(RuntimeError, match="All LLM providers failed"):
        router.call([{"role": "user", "content": "synthetic"}])
    assert primary.calls == fallback.calls == 1


class BlockingAdapter(MockTicketActionAdapter):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def create_reply(self, **kwargs):
        self.entered.set()
        assert self.release.wait(timeout=5)
        return super().create_reply(**kwargs)


def test_simultaneous_duplicate_execution_claims_once(tmp_path):
    db_path = str(tmp_path / "tickets.db")
    adapter = BlockingAdapter()
    first = TicketWorkflowService(
        db_path=db_path,
        adapter=adapter,
        decision_fn=make_fake_decision_fn(),
        enable_ledger=False,
    )
    ticket = first.create_ticket(TicketCreate(ticket_id="T-RACE", ticket_text="reset password"))
    first.review_ticket(ticket.ticket_id, ReviewRequest(reviewer_action=ReviewerAction.APPROVED))
    second = TicketWorkflowService(
        db_path=db_path,
        adapter=adapter,
        decision_fn=make_fake_decision_fn(),
        enable_ledger=False,
    )
    results = []

    def execute(service):
        try:
            results.append(service.execute_approved_reply(ticket.ticket_id).message)
        except Exception as exc:  # captured for cross-thread assertion
            results.append(exc)

    worker = threading.Thread(target=execute, args=(first,))
    worker.start()
    assert adapter.entered.wait(timeout=5)
    execute(second)
    adapter.release.set()
    worker.join(timeout=5)

    assert len(adapter.executed) == 1
    assert len(first.list_actions(ticket.ticket_id)) == 1
    assert any(isinstance(value, InvalidTransition) and "in_progress" in str(value) for value in results)
    assert any(isinstance(value, str) and "executed once" in value for value in results)


def test_provider_failure_becomes_failed_workflow_not_unsafe_auto(tmp_path):
    service = TicketWorkflowService(
        db_path=str(tmp_path / "tickets.db"),
        decision_fn=make_fake_decision_fn(raise_error=TimeoutError()),
        enable_ledger=False,
    )
    record = service.create_ticket(TicketCreate(ticket_id="T-PROVIDER-DOWN", ticket_text="reset password"))
    assert record.workflow_status.value == "failed"
    assert record.decision == "UNKNOWN"
    assert service.list_actions(record.ticket_id) == []
