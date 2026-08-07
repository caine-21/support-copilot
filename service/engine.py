"""Ticket workflow engine: create/run → query → review → idempotent mock action.

Persistence + audit + idempotency live here; the heavy agent stack is only
imported inside default_decision_fn, so tests inject a fake decision port and
run fully offline.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Optional, Protocol

from .action_adapter import MockTicketActionAdapter, TicketActionAdapter
from .domain import (
    ActionStatus,
    Decision,
    ReviewOutcome,
    ReviewRequest,
    ReviewStatus,
    ReviewerAction,
    TicketCreate,
    TicketRecord,
    WorkflowStatus,
    utc_now,
)
from .repository import (
    InvalidTransition,
    NoEvidenceGate,
    TicketNotFound,
    TicketRepository,
)

# Decision port: (ticket_text, ticket_id, user_id, customer_context, ledger) -> result dict
DecisionFn = Callable[..., dict[str, Any]]


def default_decision_fn(
    ticket_text: str,
    ticket_id: str,
    user_id: str,
    customer_context: Optional[dict[str, Any]] = None,
    ledger: Any = None,
) -> dict[str, Any]:
    """Run the existing support decision pipeline (agent_loop.run_agent)."""
    from agent.agent_loop import run_agent

    return run_agent(
        ticket_text,
        ticket_id=ticket_id,
        user_id=user_id,
        customer_context=customer_context,
        ledger=ledger,
    )


def _risk_level(result: dict[str, Any]) -> str:
    priority = result.get("priority")
    if priority:
        return str(priority)
    return {
        Decision.ESCALATE_L2.value: "high",
        Decision.ESCALATE_L1.value: "medium",
    }.get(result.get("action"), "low")


def _derive_evidence(result: dict[str, Any]) -> list[Any]:
    return result.get("kb_grounding") or []


def _derive_grounding_safe(result: dict[str, Any]) -> Optional[bool]:
    gc = result.get("grounding_check") or {}
    if isinstance(gc, dict) and gc.get("auto_reply_safe") is not None:
        return bool(gc.get("auto_reply_safe"))
    return None


def _action_type_for(decision: str) -> str:
    if decision == Decision.AUTO_REPLY.value:
        return "create_reply"
    if decision in (Decision.ESCALATE_L1.value, Decision.ESCALATE_L2.value):
        return "create_escalation"
    return "create_escalation"  # conservative default for unknown decisions


class TicketWorkflowService:
    def __init__(
        self,
        repo: Optional[TicketRepository] = None,
        decision_fn: Optional[DecisionFn] = None,
        adapter: Optional[TicketActionAdapter] = None,
        db_path: Optional[str] = None,
        enable_ledger: bool = True,
    ):
        self.repo = repo or TicketRepository(db_path)
        self.decision_fn = decision_fn or default_decision_fn
        self.adapter = adapter or MockTicketActionAdapter()
        self.enable_ledger = enable_ledger

    # ── create + run ─────────────────────────────────────────────────────────
    def create_ticket(self, payload: TicketCreate) -> TicketRecord:
        ticket_id = (payload.ticket_id or f"T-{uuid.uuid4().hex[:8].upper()}")
        normalized = payload.ticket_text.strip()
        if not normalized:
            raise InvalidTransition("ticket_text must be non-empty after normalization")

        try:
            self.repo.get_ticket(ticket_id)
            raise InvalidTransition(f"ticket {ticket_id} already exists — duplicate create rejected")
        except TicketNotFound:
            pass

        now = utc_now()
        record = TicketRecord(
            ticket_id=ticket_id,
            request_payload=payload.model_dump(),
            normalized_input=normalized,
            workflow_status=WorkflowStatus.CREATED,
            review_status=ReviewStatus.NOT_REQUIRED,
            workflow_version=payload.workflow_version,
            created_at=now,
            updated_at=now,
        )
        self.repo.save_ticket(record)

        record.workflow_status = WorkflowStatus.RUNNING
        self.repo.update_ticket(record)

        ledger = self._make_ledger(ticket_id)
        try:
            result = self.decision_fn(
                normalized,
                ticket_id=ticket_id,
                user_id=payload.user_id,
                customer_context=payload.customer_context,
                ledger=ledger,
            )
        except Exception as exc:  # decision flow failed — record failure, never fake success
            record.workflow_status = WorkflowStatus.FAILED
            record.decision = Decision.UNKNOWN.value
            record.decision_reason = f"decision_flow_error: {exc}"
            if ledger is not None:
                ledger.finalize({"mode": "service-api", "ticket_id": ticket_id, "status": "failed"})
            self.repo.update_ticket(record)
            return record

        action = result.get("action") or Decision.UNKNOWN.value
        record.decision = action
        record.decision_reason = result.get("reason")
        record.risk_level = _risk_level(result)
        record.retrieved_evidence = _derive_evidence(result)
        record.grounding_safe = _derive_grounding_safe(result)
        record.draft_response = result.get("draft_reply")
        record.workflow_status = WorkflowStatus.COMPLETED
        record.action_type = _action_type_for(action)
        record.idempotency_key = self._idempotency_key(ticket_id, payload.workflow_version, record.action_type)
        record.review_status = ReviewStatus.PENDING
        record.action_status = ActionStatus.PENDING.value

        if ledger is not None:
            ledger.log_output(ticket_id, {
                "action": action,
                "grounding": result.get("grounding"),
                "grounding_check": result.get("grounding_check"),
                "intent_set": result.get("intent_set", []),
                "routing_signals": result.get("routing_signals", []),
            })
            ledger.finalize({"mode": "service-api", "ticket_id": ticket_id, "decision": action})
            record.run_id = ledger.run_id
        self.repo.update_ticket(record)
        return record

    # ── query ────────────────────────────────────────────────────────────────
    def get_ticket(self, ticket_id: str) -> TicketRecord:
        return self.repo.get_ticket(ticket_id)

    def list_actions(self, ticket_id: str):
        return self.repo.list_actions(ticket_id)

    # ── review + idempotent action ───────────────────────────────────────────
    def review_ticket(self, ticket_id: str, req: ReviewRequest) -> ReviewOutcome:
        ticket = self.repo.get_ticket(ticket_id)

        if ticket.workflow_status == WorkflowStatus.FAILED:
            raise InvalidTransition("cannot review a failed workflow")
        if ticket.workflow_status != WorkflowStatus.COMPLETED:
            raise InvalidTransition("workflow not completed — nothing to review")

        # Already reviewed: idempotent return, never re-execute the action.
        if ticket.review_status in (ReviewStatus.APPROVED, ReviewStatus.EDITED):
            actions = self.repo.list_actions(ticket_id)
            last = actions[-1] if actions else None
            return ReviewOutcome(
                ticket=ticket,
                action=last,
                message="already reviewed — no re-execution",
            )
        if ticket.review_status == ReviewStatus.REJECTED:
            return ReviewOutcome(
                ticket=ticket, message="already rejected — no action taken"
            )

        if req.reviewer_action == ReviewerAction.REJECTED:
            ticket.review_status = ReviewStatus.REJECTED
            ticket.reviewer_action = ReviewerAction.REJECTED.value
            ticket.action_status = ActionStatus.SKIPPED.value
            self.repo.update_ticket(ticket)
            return ReviewOutcome(ticket=ticket, message="rejected — no action taken")

        # approved / edited → execute the mock action once (idempotency key)
        action_type = ticket.action_type or _action_type_for(ticket.decision or "")
        idem_key = self._idempotency_key(ticket.ticket_id, ticket.workflow_version, action_type)

        existing = self.repo.get_action_by_key(idem_key)
        if existing is not None and existing.status == ActionStatus.EXECUTED:
            ticket.review_status = (
                ReviewStatus.EDITED if req.reviewer_action == ReviewerAction.EDITED
                else ReviewStatus.APPROVED
            )
            ticket.reviewer_action = req.reviewer_action.value
            ticket.action_status = ActionStatus.DUPLICATE.value
            self.repo.update_ticket(ticket)
            return ReviewOutcome(
                ticket=ticket, action=existing,
                message="idempotent hit — action already executed once",
            )
        if existing is not None and existing.status == ActionStatus.FAILED:
            # Strategy B: a FAILED attempt must not be silently retried into an
            # IntegrityError (UNIQUE idempotency key). Explicit manual resolution.
            raise InvalidTransition("previous_execution_failed — manual retry required")

        # Evidence gate + adapter execution + record (shared with execute_approved_reply).
        draft = req.edited_draft if req.reviewer_action == ReviewerAction.EDITED and req.edited_draft else (ticket.draft_response or "")
        record = self._perform_approved_action(
            ticket, idem_key=idem_key, action_type=action_type,
            draft=draft, review_decision=req.reviewer_action.value,
        )
        ticket.review_status = (
            ReviewStatus.EDITED if req.reviewer_action == ReviewerAction.EDITED
            else ReviewStatus.APPROVED
        )
        ticket.reviewer_action = req.reviewer_action.value
        self.repo.update_ticket(ticket)
        return ReviewOutcome(
            ticket=ticket, action=record,
            message=f"{action_type} executed once (mock) — action {record.status.value}",
        )

    def execute_approved_reply(self, ticket_id: str) -> ReviewOutcome:
        """Executor-only: perform the human-approved mock reply for a ticket.

        Loads persisted approval state. Never accepts caller-supplied content or
        an approval flag — approval, evidence and idempotency all come from the
        server-side persisted ticket/action records.
        """
        ticket = self.repo.get_ticket(ticket_id)
        if ticket.review_status == ReviewStatus.REJECTED:
            raise InvalidTransition("review rejected — action not executed")
        if ticket.review_status != ReviewStatus.APPROVED:
            raise InvalidTransition("approval_required — no persisted human approval")

        action_type = ticket.action_type or _action_type_for(ticket.decision or "")
        idem_key = self._idempotency_key(ticket.ticket_id, ticket.workflow_version, action_type)
        existing = self.repo.get_action_by_key(idem_key)
        if existing is not None and existing.status == ActionStatus.EXECUTED:
            return ReviewOutcome(
                ticket=ticket, action=existing,
                message="already executed — idempotent, adapter not re-invoked",
            )
        if existing is not None and existing.status == ActionStatus.FAILED:
            # Strategy B: a FAILED attempt is a terminal failure state. It is
            # never "already_executed", and an auto retry is NOT re-invoked
            # (the UNIQUE idempotency key cannot hold two attempts). Explicit
            # manual resolution required.
            raise InvalidTransition("previous_execution_failed — manual retry required")

        # Approved content = the persisted reviewed draft; caller cannot supply text.
        draft = ticket.draft_response or ""
        record = self._perform_approved_action(
            ticket, idem_key=idem_key, action_type=action_type,
            draft=draft, review_decision=ticket.reviewer_action or ReviewerAction.APPROVED.value,
        )
        return ReviewOutcome(
            ticket=ticket, action=record,
            message=f"execute_approved_reply: {action_type} executed once (mock)",
        )

    def _perform_approved_action(
        self, ticket: TicketRecord, *, idem_key: str, action_type: str,
        draft: str, review_decision: str,
    ) -> ActionRecord:
        """Execute the approved mock action once: evidence gate -> adapter -> record.

        Shared by review_ticket (approved/edited) and execute_approved_reply so the
        authorization policy has a single source of truth.
        """
        # Evidence gate: an AUTO_REPLY with no grounding evidence may not be sent,
        # even after human approval.
        if ticket.decision == Decision.AUTO_REPLY.value and ticket.grounding_safe is not True:
            raise NoEvidenceGate(
                f"ticket {ticket.ticket_id} decision=AUTO_REPLY but grounding_safe={ticket.grounding_safe} — "
                "evidence gate blocks reply; missing evidence cannot bypass the gate"
            )
        try:
            if action_type == "create_reply":
                result = self.adapter.create_reply(
                    ticket_id=ticket.ticket_id,
                    draft=draft,
                    evidence=ticket.retrieved_evidence or [],
                )
            else:
                result = self.adapter.create_escalation(
                    ticket_id=ticket.ticket_id,
                    level=ticket.decision or "ESCALATE_L1",
                    reason=ticket.decision_reason or "",
                    evidence=ticket.retrieved_evidence or [],
                )
        except Exception as exc:  # adapter failure → record it, never mark success
            self.repo.record_action(
                idempotency_key=idem_key,
                ticket_id=ticket.ticket_id,
                action_type=action_type,
                review_decision=review_decision,
                status=ActionStatus.FAILED,
                error=str(exc),
            )
            ticket.action_status = ActionStatus.FAILED.value
            self.repo.update_ticket(ticket)
            raise

        record = self.repo.record_action(
            idempotency_key=idem_key,
            ticket_id=ticket.ticket_id,
            action_type=action_type,
            review_decision=review_decision,
            status=ActionStatus.EXECUTED,
            result=result,
        )
        ticket.action_status = ActionStatus.EXECUTED.value
        ticket.idempotency_key = idem_key
        self.repo.update_ticket(ticket)
        return record

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _idempotency_key(ticket_id: str, workflow_version: int, action_type: str) -> str:
        return f"{ticket_id}:{workflow_version}:{action_type}"

    def _make_ledger(self, ticket_id: str):
        if not self.enable_ledger:
            return None
        try:
            from agent.run_ledger import RunLedger

            return RunLedger(tag="service-api", meta={"ticket_id": ticket_id})
        except Exception:
            return None
