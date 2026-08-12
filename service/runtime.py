"""A6 composition root: safe decision port, readiness, and release metadata."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from app.contracts.incoming_request import Channel, IncomingRequest
from app.runtime.run_a1 import run_a1

from .config import RuntimeSettings


ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "faq" / "acme_collab_faq.json"


def _prompt_injection_detected(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    markers = (
        "ignore all previous instructions",
        "ignore previous instructions",
        "ignore system instructions",
        "reveal system prompt",
        "show system prompt",
        "reveal system secrets",
        "developer message",
    )
    return any(marker in normalized for marker in markers)


class _DeterministicKnowledgeGateway:
    """Provider-free retrieval boundary for public/demo execution."""

    backend = "local-deterministic"

    def execute(self, _call_id, tool_name, raw_arguments, _runtime, turn_index, _retry_count=0):
        from agent import kb
        from agent.tooling import ToolResult, ToolStatus

        if tool_name != "search_knowledge_base":
            return ToolResult(status=ToolStatus.FORBIDDEN, error_code="deterministic_tool_not_allowed")
        query = raw_arguments.get("query") if isinstance(raw_arguments, dict) else None
        top_k = raw_arguments.get("top_k", 3) if isinstance(raw_arguments, dict) else 3
        if not isinstance(query, str) or not query or not isinstance(top_k, int) or not 1 <= top_k <= 5:
            return ToolResult(status=ToolStatus.INVALID_ARGUMENTS, error_code="invalid_tool_arguments")
        rows = kb.search(query, top_k=top_k, allow_llm=False)
        return ToolResult(
            status=ToolStatus.SUCCESS if rows else ToolStatus.NOT_FOUND,
            data=rows,
            error_code=None if rows else "knowledge_not_found",
        )


def kb_version() -> str:
    try:
        payload = KB_PATH.read_bytes()
        json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "unavailable"
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def deterministic_decision_fn(
    ticket_text: str,
    ticket_id: str,
    user_id: str,
    customer_context: dict[str, Any] | None = None,
    ledger: Any = None,
) -> dict[str, Any]:
    """Provider-free public/demo decision path through canonical ``run_a1``.

    The conversion preserves the service's legacy result envelope while the
    authorization owner remains A1's existing deterministic gate.
    """
    if _prompt_injection_detected(ticket_text):
        return {
            "action": "ESCALATE_L2",
            "reason": "prompt_injection_pattern",
            "priority": "high",
            "intent": "security_review",
            "intent_set": ["security_review"],
            "kb_grounding": [],
            "grounding": "none",
            "grounding_check": {"auto_reply_safe": False, "reason_codes": ["prompt_injection_pattern"]},
            "draft_reply": "",
            "routing_signals": ["prompt_injection_pattern"],
            "trace": [
                {"event_type": "prompt_injection_detected", "component": "a6_input_guard", "reason_codes": ["prompt_injection_pattern"], "payload": {}},
                {"event_type": "authorization_decided", "component": "a6_input_guard", "reason_codes": ["human_only"], "payload": {"action": "ESCALATE_L2"}},
            ],
            "model_version": "none:deterministic",
        }

    result = run_a1(IncomingRequest(
        request_id=ticket_id,
        channel=Channel.TICKET,
        raw_text=ticket_text,
        sender_context=customer_context,
        metadata={"source": "service_demo"},
    ), tool_gateway=_DeterministicKnowledgeGateway())
    evidence: list[dict[str, Any]] = []
    for lane in result.lane_results.values():
        evidence.extend(lane.get("evidence", []))
    action = result.authorization_status
    if action not in {"AUTO_REPLY", "ESCALATE_L1", "ESCALATE_L2"}:
        action = "ESCALATE_L1"
    grounding = result.grounding_status or {}
    proposal = result.proposed_action or {}
    converted = {
        "action": action,
        "reason": ",".join(
            code
            for event in result.trace
            for code in event.get("reason_codes", [])
        ) or "deterministic_a1_authorization",
        "priority": "high" if action == "ESCALATE_L2" else "medium" if action == "ESCALATE_L1" else "low",
        "intent": result.intents[0] if result.intents else "unknown",
        "intent_set": result.intents,
        "kb_grounding": evidence,
        "grounding": (
            "strong" if grounding.get("auto_reply_safe") else
            "weak" if evidence else "none"
        ),
        "grounding_check": grounding,
        "draft_reply": proposal.get("draft", ""),
        "routing_signals": [key for key, value in result.risk_signals.items() if value],
        "trace": result.trace,
        "model_version": "none:deterministic",
    }
    if ledger is not None:
        for event in result.trace:
            ledger.log_step(ticket_id, event.get("event_type", "a1_event"), event)
    return converted


def runtime_decision_fn(settings: RuntimeSettings) -> Callable[..., dict[str, Any]]:
    if not settings.enable_provider_calls:
        return deterministic_decision_fn

    def provider_decision(
        ticket_text: str,
        ticket_id: str,
        user_id: str,
        customer_context: dict[str, Any] | None = None,
        ledger: Any = None,
    ) -> dict[str, Any]:
        from agent.agent_loop import run_agent

        return run_agent(
            ticket_text,
            ticket_id=ticket_id,
            user_id=user_id,
            customer_context=customer_context,
            ledger=ledger,
            support_agent_mode="tool_loop" if settings.enable_tool_loop else "legacy",
            multi_agent_mode="shadow" if settings.enable_multi_agent_shadow else "off",
        )

    return provider_decision


def readiness(service, settings: RuntimeSettings) -> tuple[dict[str, Any], bool]:
    dependencies: dict[str, str] = {}
    try:
        service.repo.ping()
        dependencies["database"] = "ok"
    except Exception:
        dependencies["database"] = "error"

    current_kb = kb_version()
    dependencies["knowledge_base"] = "ok" if current_kb != "unavailable" else "error"
    if settings.expected_kb_version and settings.expected_kb_version != current_kb:
        dependencies["knowledge_base"] = "version_mismatch"
    dependencies["api_auth"] = "ok" if settings.protected_api_ready else "missing"
    if settings.enable_provider_calls:
        import os

        dependencies["deepseek"] = "configured" if os.environ.get("DEEPSEEK_API_KEY") else "unknown_or_degraded"
        dependencies["groq"] = "configured" if os.environ.get("GROQ_API_KEY") else "unknown_or_degraded"
    else:
        dependencies["deepseek"] = "disabled"
        dependencies["groq"] = "disabled"

    core_ready = (
        dependencies["database"] == "ok"
        and dependencies["knowledge_base"] == "ok"
        and settings.protected_api_ready
    )
    return {
        "status": "ready" if core_ready else "not_ready",
        "dependencies": dependencies,
        "kb_version": current_kb,
        "schema_version": settings.schema_version,
    }, core_ready


def version_payload(settings: RuntimeSettings) -> dict[str, str]:
    return {
        "app_version": settings.app_version,
        "git_sha": settings.git_sha,
        "deployment_mode": settings.deployment_mode.value,
        "build_time": settings.build_time,
        "schema_version": settings.schema_version,
        "policy_version": settings.policy_version,
        "prompt_version": settings.prompt_version,
        "kb_version": kb_version(),
    }
