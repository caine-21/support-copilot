"""Typed, read-only support tools shared by local and MCP backends.

This module is intentionally below the agent loop: domain services contain the
business lookup, adapters only translate protocols, and the gateway validates
untrusted model arguments before execution.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ToolStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    INVALID_ARGUMENTS = "invalid_arguments"
    FORBIDDEN = "forbidden"
    TIMEOUT = "timeout"
    ERROR = "error"


class EvidenceReference(BaseModel):
    source_id: str
    source_type: Literal["knowledge_base", "customer_context", "ticket_history", "ticket"]
    locator: str


class ToolResult(BaseModel):
    status: ToolStatus
    data: Any = None
    evidence: list[EvidenceReference] = Field(default_factory=list)
    error_code: str | None = None
    retryable: bool = False


class SearchKnowledgeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=3, ge=1, le=5)


class CustomerContextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_context: dict[str, Any] = Field(default_factory=dict)


class TicketHistoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=128)


class GetTicketArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=128)


class ExecuteApprovedReplyArgs(BaseModel):
    """Executor-only action input.

    Minimal on purpose: no `approved`, `force`, `review_status` or `reply_text`
    fields. Approval, evidence, integrity and idempotency all come from
    server-side persisted state — the caller cannot pass an approval flag.
    """
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=128)


class ToolPermission(str, Enum):
    READ = "read"
    REVERSIBLE_WRITE = "reversible_write"
    EXTERNAL_OR_IRREVERSIBLE = "external_or_irreversible"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    args_model: type[BaseModel]
    permission: ToolPermission
    handler: Callable[[BaseModel, "ToolRuntime"], ToolResult]

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


@dataclass
class ToolRuntime:
    user_id: str
    ticket_text: str
    ticket_id: str = "unknown"
    customer_context: dict[str, Any] | None = None
    memory: Any = None


def search_knowledge_base(args: SearchKnowledgeArgs, _: ToolRuntime) -> ToolResult:
    from . import kb
    # `kb.search` retains legacy diagnostic printing. Stdio MCP reserves stdout
    # for JSON-RPC, so direct it to stderr at this protocol-neutral boundary.
    with contextlib.redirect_stdout(sys.stderr):
        results = kb.search(args.query, top_k=args.top_k)
    evidence = [EvidenceReference(source_id=row["doc_id"], source_type="knowledge_base", locator=row["doc_id"])
                for row in results]
    return ToolResult(status=ToolStatus.SUCCESS if results else ToolStatus.NOT_FOUND,
                      data=results, evidence=evidence,
                      error_code=None if results else "knowledge_not_found")


def get_customer_context(args: CustomerContextArgs, runtime: ToolRuntime) -> ToolResult:
    context = args.customer_context or runtime.customer_context or {}
    if not context:
        return ToolResult(status=ToolStatus.NOT_FOUND, data={}, error_code="customer_context_not_found")
    # The tool exposes only the already supplied synthetic/local context. It does
    # not decide authorization; that deterministic gate stays outside the loop.
    return ToolResult(status=ToolStatus.SUCCESS, data=context,
                      evidence=[EvidenceReference(source_id="customer_context", source_type="customer_context", locator="runtime")])


def get_ticket_history(args: TicketHistoryArgs, runtime: ToolRuntime) -> ToolResult:
    history = runtime.memory.get_history(args.user_id) if runtime.memory is not None else []
    return ToolResult(status=ToolStatus.SUCCESS, data={"past_tickets": history[-5:], "ticket_count": len(history)},
                      evidence=[EvidenceReference(source_id=args.user_id, source_type="ticket_history", locator="memory:last5")])


def get_ticket(args: GetTicketArgs, _: ToolRuntime) -> ToolResult:
    """Read a persisted ticket workflow record from the shared repository.

    Read-only. The repository DB path is resolved the same way for local and
    MCP execution (SUPPORT_DB_PATH env), so both backends see the same state.
    """
    from service.repository import TicketNotFound, TicketRepository

    try:
        repo = TicketRepository()
    except Exception:
        return ToolResult(status=ToolStatus.ERROR, data={}, error_code="ticket_repository_error")
    try:
        try:
            rec = repo.get_ticket(args.ticket_id)
        except TicketNotFound:
            return ToolResult(status=ToolStatus.NOT_FOUND, data={}, error_code="ticket_not_found")
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=rec.model_dump(),
            evidence=[EvidenceReference(source_id=args.ticket_id, source_type="ticket", locator="repository")],
        )
    except Exception:
        return ToolResult(status=ToolStatus.ERROR, data={}, error_code="ticket_repository_error")
    finally:
        try:
            repo.close()
        except Exception:
            pass


def execute_approved_reply(args: ExecuteApprovedReplyArgs, _: ToolRuntime) -> ToolResult:
    """Executor-only: perform the human-approved mock reply for a ticket.

    Reads persisted approval / evidence / idempotency from the server; never
    accepts caller-supplied content or an approval flag.
    """
    from service.engine import InvalidTransition, NoEvidenceGate, TicketWorkflowService
    from service.repository import TicketNotFound

    try:
        svc = TicketWorkflowService(enable_ledger=False)
        outcome = svc.execute_approved_reply(args.ticket_id)
    except TicketNotFound:
        return ToolResult(status=ToolStatus.NOT_FOUND, data={}, error_code="ticket_not_found")
    except NoEvidenceGate:
        return ToolResult(status=ToolStatus.FORBIDDEN, data={}, error_code="grounding_not_authorized")
    except InvalidTransition as exc:
        msg = str(exc)
        if "approval_required" in msg:
            return ToolResult(status=ToolStatus.FORBIDDEN, data={}, error_code="approval_required")
        if "rejected" in msg:
            return ToolResult(status=ToolStatus.FORBIDDEN, data={}, error_code="review_rejected")
        if "previous_execution_failed" in msg:
            return ToolResult(status=ToolStatus.ERROR, data={}, error_code="previous_execution_failed")
        if "stale_approved_draft" in msg:
            return ToolResult(status=ToolStatus.ERROR, data={}, error_code="stale_approved_draft")
        return ToolResult(status=ToolStatus.ERROR, data={}, error_code="action_not_executable")
    except Exception as exc:  # noqa: BLE001 — boundary maps any failure to the envelope
        return ToolResult(status=ToolStatus.ERROR, data={}, error_code=f"action_execution_failed:{type(exc).__name__}")

    action = outcome.action
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data={"message": outcome.message,
              "action": action.model_dump() if action is not None else None},
        evidence=[EvidenceReference(source_id=args.ticket_id, source_type="ticket", locator="execute_approved_reply")],
    )


def support_tool_registry() -> dict[str, ToolDefinition]:
    return {
        "search_knowledge_base": ToolDefinition("search_knowledge_base", "Read matching Support Copilot KB excerpts; never authorizes an action.", SearchKnowledgeArgs, ToolPermission.READ, search_knowledge_base),
        "get_customer_context": ToolDefinition("get_customer_context", "Read supplied local/synthetic customer context; never changes customer data.", CustomerContextArgs, ToolPermission.READ, get_customer_context),
        "get_ticket": ToolDefinition("get_ticket", "Read a persisted ticket workflow record; never authorizes or mutates.", GetTicketArgs, ToolPermission.READ, get_ticket),
        "get_ticket_history": ToolDefinition("get_ticket_history", "Read recent in-memory ticket history for one user.", TicketHistoryArgs, ToolPermission.READ, get_ticket_history),
    }


def executor_tool_registry() -> dict[str, ToolDefinition]:
    """Executor-only side-effect registry. Modeled as external/irreversible even
    though the adapter is mock, because it simulates a real external side effect.

    Kept SEPARATE from support_tool_registry so specialists and the agent tool
    loop can never discover or force these tools.
    """
    return {
        "execute_approved_reply": ToolDefinition(
            "execute_approved_reply",
            "Execute the human-approved mock reply for a ticket (executor-only; reads persisted approval, never caller-supplied).",
            ExecuteApprovedReplyArgs, ToolPermission.EXTERNAL_OR_IRREVERSIBLE, execute_approved_reply,
        ),
    }


def tools_for_scope(scope: str) -> list[ToolDefinition]:
    """Capability discovery by scope. Specialists never see the executor set."""
    if scope == "executor":
        return list(executor_tool_registry().values())
    return list(support_tool_registry().values())


def executor_gateway(backend: Literal["local", "mcp"] = "local", **kw) -> ToolGateway:
    """Executor-scoped gateway: discovers/executes only the approval-gated
    side-effect tool. Specialists are never constructed with this gateway."""
    return ToolGateway(
        executor_tool_registry(), backend=backend,
        allowed_permissions={ToolPermission.EXTERNAL_OR_IRREVERSIBLE}, **kw,
    )


# Specialist capability boundaries (A2A). Knowledge is exercised through a
# scoped gateway in A1. Support's allowlist is policy-prepared but NOT
# exercised yet: A1 Support receives evidence as input and does not call tools.
SPECIALIST_TOOL_ALLOWLISTS: dict[str, list[str]] = {
    "knowledge": ["search_knowledge_base"],
    "support": ["search_knowledge_base", "get_customer_context", "get_ticket_history"],
}


def tools_for_specialist(registry: dict[str, ToolDefinition], specialist: str) -> list[ToolDefinition]:
    """Discovery view: allowlist ∩ READ permission. Write tools are never shown."""
    allowed = set(SPECIALIST_TOOL_ALLOWLISTS.get(specialist, ()))
    return [d for d in registry.values() if d.permission == ToolPermission.READ and d.name in allowed]


class ScopedToolGateway:
    """Specialist-scoped gateway: BOTH discovery and execution are bounded to the
    allowlist. Forcing a non-allowlisted tool fails FORBIDDEN before the backend
    runs, so capability withholding holds even if the caller bypasses discovery.

    backend selection lives here (composition root), never in the Specialist.
    """

    def __init__(
        self,
        registry: dict[str, ToolDefinition] | None = None,
        *,
        specialist: str | None = None,
        allowed_tool_names: list[str] | None = None,
        backend: Literal["local", "mcp"] = "local",
        tool_timeout_seconds: float = 3.0,
        ledger: Any = None,
        allowed_permissions: set[ToolPermission] | None = None,
    ):
        self._registry = registry or support_tool_registry()
        if allowed_tool_names is None:
            allowed_tool_names = SPECIALIST_TOOL_ALLOWLISTS.get(specialist or "", [])
        self._allowed = set(allowed_tool_names)
        self._gateway = ToolGateway(
            registry=self._registry, backend=backend,
            tool_timeout_seconds=tool_timeout_seconds, ledger=ledger,
            allowed_permissions=allowed_permissions,
        )

    @property
    def backend(self) -> str:
        return self._gateway.backend

    def available_tools(self) -> list[ToolDefinition]:
        return [d for d in self._gateway.available_tools() if d.name in self._allowed]

    def execute(
        self, call_id: str, tool_name: str, raw_arguments: dict[str, Any],
        runtime: ToolRuntime, turn_index: int, retry_count: int = 0,
    ) -> ToolResult:
        if tool_name not in self._allowed:
            return ToolResult(
                status=ToolStatus.FORBIDDEN, data={},
                error_code="specialist_tool_not_allowed",
            )
        return self._gateway.execute(call_id, tool_name, raw_arguments, runtime, turn_index, retry_count)


def _redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    # Ticket text and context can contain customer data; ledger records keys and
    # lengths rather than raw values.
    return {key: (f"<redacted:{len(value)}>" if isinstance(value, str) else "<redacted-object>" if isinstance(value, dict) else value)
            for key, value in arguments.items()}


class LocalToolAdapter:
    backend = "local"
    def execute(self, definition: ToolDefinition, arguments: BaseModel, runtime: ToolRuntime, timeout_seconds: float) -> ToolResult:
        # Do not use a context manager here: its __exit__ waits for a timed-out
        # worker. Registry tools are read-only, so an abandoned result cannot
        # cause a write after the caller has safely escalated.
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(definition.handler, arguments, runtime)
        try:
            result = future.result(timeout=timeout_seconds)
        except FutureTimeout:
            future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            return ToolResult(status=ToolStatus.TIMEOUT, error_code="tool_timeout", retryable=True)
        except Exception:
            pool.shutdown(wait=False, cancel_futures=True)
            return ToolResult(status=ToolStatus.ERROR, error_code="tool_execution_failed", retryable=True)
        pool.shutdown(wait=False, cancel_futures=True)
        return result


class MCPToolAdapter:
    """Stdio MCP client adapter. MCP objects never escape this boundary.

    Startup (spawn + initialize + list_tools) has a DEDICATED deadline so a
    cold-start tail never consumes the tool-execution timeout. The tool call
    itself keeps the caller-supplied timeout. Both are bounded separately.
    """
    backend = "mcp"

    def __init__(self, command: str | None = None, args: list[str] | None = None,
                 cwd: str | None = None, env: dict | None = None,
                 startup_deadline_s: float = 30.0):
        # Use the running interpreter rather than the Windows `py` launcher so
        # the SDK can terminate exactly the process it created on stdio close.
        command = command or sys.executable
        self.command = command
        self.args = args or ["-u", "-B", "-m", "agent.support_mcp_server"]
        self.cwd = cwd or os.path.dirname(os.path.dirname(__file__))
        # Default to inheriting the parent env so config like SUPPORT_DB_PATH
        # reaches the subprocess for shared-state parity.
        self.env = env if env is not None else dict(os.environ)
        self._startup_deadline_s = startup_deadline_s

    def execute(self, definition: ToolDefinition, arguments: BaseModel, _: ToolRuntime, timeout_seconds: float) -> ToolResult:
        async def call() -> ToolResult:
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=self.command, args=self.args, cwd=self.cwd, env=self.env)
            # The MCP SDK defaults errlog to the parent's sys.stderr; on Windows
            # a child writing non-ASCII server diagnostics ([KB] ...) to that
            # shared console stream raises EINVAL. Route server logs to NUL —
            # error semantics still flow via the MCP protocol.
            devnull = open(os.devnull, "w", encoding="utf-8")
            try:
                async with stdio_client(params, errlog=devnull) as (read, write):
                    async with ClientSession(read, write) as session:
                        # Startup phase: bounded by its own deadline (cold import dominated).
                        await asyncio.wait_for(session.initialize(), timeout=self._startup_deadline_s)
                        listed = await asyncio.wait_for(session.list_tools(), timeout=self._startup_deadline_s)
                        if definition.name not in {tool.name for tool in listed.tools}:
                            return ToolResult(status=ToolStatus.NOT_FOUND, error_code="mcp_tool_not_found")
                        # Tool-execution phase: caller-supplied timeout only.
                        response = await asyncio.wait_for(
                            session.call_tool(definition.name, arguments.model_dump()),
                            timeout=timeout_seconds,
                        )
                        if getattr(response, "is_error", False):
                            return ToolResult(status=ToolStatus.ERROR, error_code="mcp_tool_error", retryable=True)
                        structured = getattr(response, "structured_content", None)
                        # FastMCP serializes a plain dictionary into a JSON text
                        # content block unless an explicit output schema is given.
                        # Normalize that SDK representation back to our contract.
                        if structured is None:
                            text_blocks = [getattr(item, "text", None) for item in getattr(response, "content", [])]
                            structured = json.loads(next(text for text in text_blocks if text is not None))
                        return ToolResult.model_validate(structured)
            finally:
                devnull.close()
        try:
            return asyncio.run(asyncio.wait_for(call(), timeout=self._startup_deadline_s + timeout_seconds))
        except TimeoutError:
            return ToolResult(status=ToolStatus.TIMEOUT, error_code="mcp_timeout", retryable=True)
        except Exception as exc:
            return ToolResult(status=ToolStatus.ERROR, error_code=f"mcp_connection_{type(exc).__name__.lower()}", retryable=True)


class ToolGateway:
    def __init__(self, registry: dict[str, ToolDefinition] | None = None, backend: Literal["local", "mcp"] = "local", *, tool_timeout_seconds: float = 3.0, max_output_bytes: int = 20_000, ledger: Any = None, allowed_permissions: set[ToolPermission] | None = None):
        self.registry = registry or support_tool_registry()
        self.adapter = LocalToolAdapter() if backend == "local" else MCPToolAdapter()
        # Default is READ-only (the specialist/agent plane). The executor scope
        # passes {EXTERNAL_OR_IRREVERSIBLE} for the approval-gated action.
        self.allowed_permissions = allowed_permissions or {ToolPermission.READ}
        self.backend, self.tool_timeout_seconds, self.max_output_bytes, self.ledger = backend, tool_timeout_seconds, max_output_bytes, ledger

    def available_tools(self) -> list[ToolDefinition]:
        return [d for d in self.registry.values() if d.permission in self.allowed_permissions]

    def execute(self, call_id: str, tool_name: str, raw_arguments: dict[str, Any], runtime: ToolRuntime, turn_index: int, retry_count: int = 0) -> ToolResult:
        definition = self.registry.get(tool_name)
        if definition is None:
            return ToolResult(status=ToolStatus.NOT_FOUND, error_code="tool_not_registered")
        if definition.permission not in self.allowed_permissions:
            return ToolResult(status=ToolStatus.FORBIDDEN, error_code="tool_permission_denied")
        try:
            arguments = definition.args_model.model_validate(raw_arguments)
        except ValidationError:
            return ToolResult(status=ToolStatus.INVALID_ARGUMENTS, error_code="invalid_tool_arguments")
        started = time.monotonic()
        # Read tools may receive one bounded retry. The registry currently does
        # not expose writes, so this rule cannot replay a side effect.
        attempts = retry_count
        result = self.adapter.execute(definition, arguments, runtime, self.tool_timeout_seconds)
        while result.retryable and definition.permission == ToolPermission.READ and attempts < 1:
            attempts += 1
            result = self.adapter.execute(definition, arguments, runtime, self.tool_timeout_seconds)
        encoded = json.dumps(result.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > self.max_output_bytes:
            result = ToolResult(status=ToolStatus.ERROR, error_code="tool_output_too_large")
        if self.ledger is not None:
            self.ledger.log_tool_execution(runtime.ticket_id, turn_index=turn_index, call_id=call_id, tool_name=tool_name, backend=self.backend, redacted_arguments=_redact_arguments(raw_arguments), result_status=result.status.value, evidence=[item.model_dump() for item in result.evidence], latency_ms=round((time.monotonic()-started)*1000, 2), retry_count=attempts)
        return result
