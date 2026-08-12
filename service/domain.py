"""Domain types for the ticket workflow slice.

The decision set mirrors agent/reasoner.py string constants. IMPORTANT: the
reasoner emits exactly {AUTO_REPLY, ESCALATE_L1, ESCALATE_L2} — there is no
ABSTAIN in the source. UNKNOWN is a service-level fallback for runs where the
decision flow itself failed (never emitted by the reasoner).
"""
from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class Decision(str, Enum):
    """Real decision set from agent/reasoner.py (+ service-level UNKNOWN)."""

    AUTO_REPLY = "AUTO_REPLY"
    ESCALATE_L1 = "ESCALATE_L1"
    ESCALATE_L2 = "ESCALATE_L2"
    UNKNOWN = "UNKNOWN"  # service-level only: decision flow failed


class WorkflowStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending_review"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ReviewerAction(str, Enum):
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ActionStatus(str, Enum):
    PENDING = "pending"
    READY_FOR_EXECUTION = "ready_for_execution"
    IN_PROGRESS = "in_progress"
    EXECUTED = "executed"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    SKIPPED = "skipped"


class TicketCreate(BaseModel):
    """Inbound ticket request body."""

    model_config = ConfigDict(extra="forbid")

    ticket_text: str = Field(..., min_length=1, max_length=4_000, description="raw ticket text")
    ticket_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="caller-supplied id; auto-generated if omitted",
    )
    user_id: str = Field(default="U-?", min_length=1, max_length=128, description="customer id for history lookup")
    customer_context: Optional[dict[str, Any]] = Field(default=None)
    workflow_version: int = Field(default=1, ge=1)


class CustomerDemoProfile(BaseModel):
    """Non-sensitive, one-session selectors for public experimentation."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["personal", "team", "enterprise"] = "team"
    region: Literal["US", "EU", "APAC", "CN"] = "US"
    role: Literal["member", "admin", "owner"] = "member"


class CustomerTicketRequest(BaseModel):
    """Minimal public payload for the customer-facing web channel."""

    model_config = ConfigDict(extra="forbid")

    ticket_text: str = Field(..., min_length=1, max_length=2_000)
    profile: CustomerDemoProfile | None = None


class CustomerTicketResponse(BaseModel):
    """Redacted response contract for an anonymous customer channel."""

    ticket_id: str
    status: str
    decision: Optional[str] = None
    reply: Optional[str] = None
    grounding_safe: Optional[bool] = None
    reason: Optional[str] = None
    next_step: str


class ReviewRequest(BaseModel):
    """Human review of a completed ticket before the mock action executes."""

    model_config = ConfigDict(extra="forbid")

    reviewer_action: ReviewerAction
    reviewer_id: str = Field(
        default="reviewer", min_length=1, max_length=128,
        pattern=r"^[A-Za-z0-9._:@+-]+$",
    )
    reason_code: Optional[str] = Field(
        default=None, description="e.g. safe_to_send / content_risk / policy_violation"
    )
    edited_draft: Optional[str] = Field(
        default=None, max_length=4_000, description="only for reviewer_action=edited"
    )


class TicketRecord(BaseModel):
    """Persisted state for one ticket workflow (see §7.3 of the upgrade brief)."""

    ticket_id: str
    request_payload: dict[str, Any]
    normalized_input: str
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    risk_level: Optional[str] = None
    retrieved_evidence: Optional[list[Any]] = None
    draft_response: Optional[str] = None
    grounding_safe: Optional[bool] = None
    workflow_status: WorkflowStatus
    review_status: ReviewStatus
    reviewer_action: Optional[str] = None
    idempotency_key: Optional[str] = None
    action_status: Optional[str] = None
    workflow_version: int = 1
    action_type: Optional[str] = None
    run_id: Optional[str] = None
    # A4 review checkpoint: the reviewed content that was approved, its SHA-256
    # binding, and review metadata. NULL until a human approves/edits.
    approved_payload: Optional[str] = None
    approved_payload_hash: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_version: Optional[int] = None
    created_at: str
    updated_at: str


class ActionRecord(BaseModel):
    """Append-only audit of one mock action attempt."""

    id: int
    idempotency_key: str
    ticket_id: str
    action_type: str
    review_decision: str
    status: ActionStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str


class ReviewOutcome(BaseModel):
    ticket: TicketRecord
    action: Optional[ActionRecord] = None
    message: str
