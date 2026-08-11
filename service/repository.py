"""SQLite repository for the ticket workflow slice.

Deliberately stdlib-only (sqlite3) ? no ORM, no external services. A ticket row
holds the workflow state; a ticket_actions row is an append-only audit record
keyed by idempotency_key, which is what makes re-execution impossible.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any, Optional

from .domain import (
    ActionRecord,
    ActionStatus,
    ReviewStatus,
    TicketRecord,
    WorkflowStatus,
    utc_now,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id         TEXT PRIMARY KEY,
  request_payload   TEXT NOT NULL,
  normalized_input  TEXT NOT NULL,
  decision          TEXT,
  decision_reason   TEXT,
  risk_level        TEXT,
  retrieved_evidence TEXT,
  draft_response    TEXT,
  grounding_safe    INTEGER,
  workflow_status   TEXT NOT NULL,
  review_status     TEXT NOT NULL,
  reviewer_action   TEXT,
  idempotency_key   TEXT,
  action_status     TEXT,
  workflow_version  INTEGER NOT NULL DEFAULT 1,
  action_type       TEXT,
  run_id            TEXT,
  approved_payload  TEXT,
  approved_payload_hash TEXT,
  reviewed_at       TEXT,
  review_version    INTEGER,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_actions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key  TEXT NOT NULL UNIQUE,
  ticket_id        TEXT NOT NULL,
  action_type      TEXT NOT NULL,
  review_decision  TEXT NOT NULL,
  status           TEXT NOT NULL,
  result           TEXT,
  error            TEXT,
  created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_actions_ticket ON ticket_actions(ticket_id);
"""

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "service", "tickets.db",
)
SCHEMA_VERSION = "2"


class TicketNotFound(Exception):
    pass


class InvalidTransition(Exception):
    """Raised on illegal state change (duplicate create, review after action?)."""


class NoEvidenceGate(Exception):
    """Raised when a mock reply would run without grounding evidence."""


class TicketRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("SUPPORT_DB_PATH") or DEFAULT_DB_PATH
        self._lock = threading.RLock()
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # Prototype-safe additive migration: existing DBs get the A4 review
        # checkpoint columns without a manual drop. Idempotent ? each ALTER is
        # skipped if the column already exists.
        for col, ddl in (
            ("approved_payload", "ALTER TABLE tickets ADD COLUMN approved_payload TEXT"),
            ("approved_payload_hash", "ALTER TABLE tickets ADD COLUMN approved_payload_hash TEXT"),
            ("reviewed_at", "ALTER TABLE tickets ADD COLUMN reviewed_at TEXT"),
            ("review_version", "ALTER TABLE tickets ADD COLUMN review_version INTEGER"),
        ):
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(tickets)").fetchall()}
            if col not in cols:
                self._conn.execute(ddl)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ping(self) -> None:
        """Readiness check: connection, schema, and the A4 integrity columns."""
        with self._lock:
            self._conn.execute("SELECT 1").fetchone()
            cols = {row[1] for row in self._conn.execute("PRAGMA table_info(tickets)").fetchall()}
        required = {"ticket_id", "approved_payload", "approved_payload_hash", "review_version"}
        if not required.issubset(cols):
            raise sqlite3.DatabaseError("ticket schema incomplete")

    # ?? tickets ?????????????????????????????????????????????????????????????
    def save_ticket(self, record: TicketRecord) -> TicketRecord:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO tickets (
                 ticket_id, request_payload, normalized_input, decision,
                 decision_reason, risk_level, retrieved_evidence, draft_response,
                 grounding_safe, workflow_status, review_status, reviewer_action,
                 idempotency_key, action_status, workflow_version, action_type,
                 run_id, approved_payload, approved_payload_hash, reviewed_at,
                 review_version, created_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.ticket_id,
                json.dumps(record.request_payload, ensure_ascii=False),
                record.normalized_input,
                record.decision,
                record.decision_reason,
                record.risk_level,
                json.dumps(record.retrieved_evidence or [], ensure_ascii=False),
                record.draft_response,
                record.grounding_safe,
                record.workflow_status.value,
                record.review_status.value,
                record.reviewer_action,
                record.idempotency_key,
                record.action_status,
                record.workflow_version,
                record.action_type,
                record.run_id,
                record.approved_payload,
                record.approved_payload_hash,
                record.reviewed_at,
                record.review_version,
                record.created_at,
                record.updated_at,
                ),
            )
            self._conn.commit()
        return record

    def get_ticket(self, ticket_id: str) -> TicketRecord:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        if row is None:
            raise TicketNotFound(ticket_id)
        return self._row_to_ticket(row)

    def list_tickets(self, limit: int = 50) -> list[TicketRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_ticket(r) for r in rows]

    def update_ticket(self, record: TicketRecord) -> TicketRecord:
        record.updated_at = utc_now()
        return self.save_ticket(record)

    # ?? actions (audit + idempotency) ???????????????????????????????????????
    def get_action_by_key(self, idempotency_key: str) -> Optional[ActionRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM ticket_actions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return self._row_to_action(row) if row else None

    def list_actions(self, ticket_id: str) -> list[ActionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ticket_actions WHERE ticket_id = ? ORDER BY id",
                (ticket_id,),
            ).fetchall()
        return [self._row_to_action(r) for r in rows]

    def record_action(
        self,
        *,
        idempotency_key: str,
        ticket_id: str,
        action_type: str,
        review_decision: str,
        status: ActionStatus,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> ActionRecord:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO ticket_actions (
                 idempotency_key, ticket_id, action_type, review_decision,
                 status, result, error, created_at
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                idempotency_key,
                ticket_id,
                action_type,
                review_decision,
                status.value,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error,
                utc_now(),
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM ticket_actions WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return self._row_to_action(row)

    def claim_action(
        self,
        *,
        idempotency_key: str,
        ticket_id: str,
        action_type: str,
        review_decision: str,
    ) -> tuple[ActionRecord, bool]:
        """Atomically claim a logical action before invoking its adapter.

        The UNIQUE key is the cross-process boundary; the lock keeps one shared
        sqlite connection transaction-safe across FastAPI worker threads.
        """
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                cur = self._conn.execute(
                    """INSERT INTO ticket_actions (
                         idempotency_key, ticket_id, action_type, review_decision,
                         status, result, error, created_at
                       ) VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        idempotency_key,
                        ticket_id,
                        action_type,
                        review_decision,
                        ActionStatus.IN_PROGRESS.value,
                        None,
                        None,
                        utc_now(),
                    ),
                )
                self._conn.commit()
                row = self._conn.execute(
                    "SELECT * FROM ticket_actions WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
                return self._row_to_action(row), True
            except sqlite3.IntegrityError:
                self._conn.rollback()
                row = self._conn.execute(
                    "SELECT * FROM ticket_actions WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if row is None:
                    raise
                return self._row_to_action(row), False
            except Exception:
                self._conn.rollback()
                raise

    def complete_action(
        self,
        idempotency_key: str,
        *,
        status: ActionStatus,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> ActionRecord:
        if status not in {ActionStatus.EXECUTED, ActionStatus.FAILED}:
            raise ValueError("claimed action can complete only as EXECUTED or FAILED")
        with self._lock:
            cur = self._conn.execute(
                """UPDATE ticket_actions
                   SET status = ?, result = ?, error = ?
                   WHERE idempotency_key = ? AND status = ?""",
                (
                    status.value,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error,
                    idempotency_key,
                    ActionStatus.IN_PROGRESS.value,
                ),
            )
            if cur.rowcount != 1:
                self._conn.rollback()
                raise InvalidTransition("action claim is not in progress")
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM ticket_actions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return self._row_to_action(row)

    # ?? helpers ?????????????????????????????????????????????????????????????
    @staticmethod
    def _row_to_ticket(row: sqlite3.Row) -> TicketRecord:
        return TicketRecord(
            ticket_id=row["ticket_id"],
            request_payload=json.loads(row["request_payload"] or "{}"),
            normalized_input=row["normalized_input"],
            decision=row["decision"],
            decision_reason=row["decision_reason"],
            risk_level=row["risk_level"],
            retrieved_evidence=json.loads(row["retrieved_evidence"] or "[]"),
            draft_response=row["draft_response"],
            grounding_safe=bool(row["grounding_safe"]) if row["grounding_safe"] is not None else None,
            workflow_status=WorkflowStatus(row["workflow_status"]),
            review_status=ReviewStatus(row["review_status"]),
            reviewer_action=row["reviewer_action"],
            idempotency_key=row["idempotency_key"],
            action_status=row["action_status"],
            workflow_version=row["workflow_version"],
            action_type=row["action_type"],
            run_id=row["run_id"],
            approved_payload=row["approved_payload"],
            approved_payload_hash=row["approved_payload_hash"],
            reviewed_at=row["reviewed_at"],
            review_version=row["review_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_action(row: sqlite3.Row) -> ActionRecord:
        return ActionRecord(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            ticket_id=row["ticket_id"],
            action_type=row["action_type"],
            review_decision=row["review_decision"],
            status=ActionStatus(row["status"]),
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=row["created_at"],
        )
