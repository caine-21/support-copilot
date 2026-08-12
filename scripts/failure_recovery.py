"""Safe local failure/recovery exercise for the public support boundary.

This uses an injected decision double, never a production provider key or
Render secret. It proves that a provider timeout is recorded as a failed
workflow and that a later request succeeds after the dependency recovers.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.config import RuntimeSettings
from service.engine import TicketWorkflowService
from service.observability import Telemetry
from service.domain import TicketCreate


class FailOnceDecision:
    def __init__(self):
        self.failed = False

    def __call__(self, ticket_text, ticket_id, user_id, customer_context=None, ledger=None):
        if not self.failed:
            self.failed = True
            raise TimeoutError("injected provider timeout")
        # The recovery leg deliberately stays provider-free. Provider taxonomy
        # and fallback behavior are covered by the existing LLMRouter tests;
        # this exercise focuses on workflow failure -> recovery semantics.
        return {
            "action": "AUTO_REPLY",
            "reason": "recovery_fixture",
            "priority": "low",
            "intent": "password_reset",
            "kb_grounding": [{"doc_id": "FAQ-account-01", "title": "Password reset"}],
            "grounding": "strong",
            "grounding_check": {"auto_reply_safe": True, "reason_codes": ["fixture_grounded"]},
            "draft_reply": "Use the password reset flow from the account page.",
            "trace": [],
        }


def run_exercise() -> dict:
    stream = io.StringIO()
    logger = logging.getLogger("support_copilot.failure_recovery")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler(stream))
    logger.propagate = False
    cfg = RuntimeSettings.from_env({"SUPPORT_DEPLOYMENT_MODE": "local"})
    telemetry = Telemetry(cfg, logger=logger)

    with tempfile.TemporaryDirectory(prefix="support-failure-recovery-") as directory:
        service = TicketWorkflowService(
            db_path=str(Path(directory) / "tickets.db"),
            decision_fn=FailOnceDecision(),
            enable_ledger=False,
            telemetry=telemetry,
        )
        failed = service.create_ticket(TicketCreate(ticket_id="T-FAILURE", ticket_text="reset password"))
        recovered = service.create_ticket(TicketCreate(ticket_id="T-RECOVERY", ticket_text="reset password"))
        service.repo.close()

    logs = stream.getvalue()
    return {
        "exercise": "provider-timeout-and-recovery",
        "injected_failure": "TimeoutError",
        "observed": {
            "failed_workflow_status": failed.workflow_status.value,
            "failed_decision": failed.decision,
            "classified_error": "provider_timeout" if "provider_timeout" in logs else "missing",
        },
        "recovery": {
            "workflow_status": recovered.workflow_status.value,
            "decision": recovered.decision,
            "grounding_safe": recovered.grounding_safe,
        },
        "secret_leakage": any(value in logs for value in ("injected provider timeout", "DEEPSEEK_API_KEY", "GROQ_API_KEY")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_exercise()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["observed"]["classified_error"] == "provider_timeout" and result["recovery"]["workflow_status"] == "completed" and not result["secret_leakage"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
