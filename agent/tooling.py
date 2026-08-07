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
    source_type: Literal["knowledge_base", "customer_context", "ticket_history"]
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


def support_tool_registry() -> dict[str, ToolDefinition]:
    return {
        "search_knowledge_base": ToolDefinition("search_knowledge_base", "Read matching Support Copilot KB excerpts; never authorizes an action.", SearchKnowledgeArgs, ToolPermission.READ, search_knowledge_base),
        "get_customer_context": ToolDefinition("get_customer_context", "Read supplied local/synthetic customer context; never changes customer data.", CustomerContextArgs, ToolPermission.READ, get_customer_context),
        "get_ticket_history": ToolDefinition("get_ticket_history", "Read recent in-memory ticket history for one user.", TicketHistoryArgs, ToolPermission.READ, get_ticket_history),
    }


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
    """Stdio MCP client adapter. MCP objects never escape this boundary."""
    backend = "mcp"
    def __init__(self, command: str | None = None, args: list[str] | None = None, cwd: str | None = None):
        # Use the running interpreter rather than the Windows `py` launcher so
        # the SDK can terminate exactly the process it created on stdio close.
        command = command or sys.executable
        self.command, self.args, self.cwd = command, args or ["-u", "-B", "-m", "agent.support_mcp_server"], cwd or os.path.dirname(os.path.dirname(__file__))

    def execute(self, definition: ToolDefinition, arguments: BaseModel, _: ToolRuntime, timeout_seconds: float) -> ToolResult:
        async def call() -> ToolResult:
            from mcp import Client
            from mcp.client.stdio import StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=self.command, args=self.args, cwd=self.cwd)
            async with Client(stdio_client(params)) as client:
                    listed = await client.list_tools()
                    if definition.name not in {tool.name for tool in listed.tools}:
                        return ToolResult(status=ToolStatus.NOT_FOUND, error_code="mcp_tool_not_found")
                    response = await client.call_tool(definition.name, arguments.model_dump())
                    if response.is_error:
                        return ToolResult(status=ToolStatus.ERROR, error_code="mcp_tool_error", retryable=True)
                    structured = response.structured_content
                    # FastMCP serializes a plain dictionary into a JSON text
                    # content block unless an explicit output schema is given.
                    # Normalize that SDK representation back to our contract.
                    if structured is None:
                        text_blocks = [getattr(item, "text", None) for item in response.content]
                        structured = json.loads(next(text for text in text_blocks if text is not None))
                    return ToolResult.model_validate(structured)
        try:
            return asyncio.run(asyncio.wait_for(call(), timeout=timeout_seconds))
        except TimeoutError:
            return ToolResult(status=ToolStatus.TIMEOUT, error_code="mcp_timeout", retryable=True)
        except Exception as exc:
            return ToolResult(status=ToolStatus.ERROR, error_code=f"mcp_connection_{type(exc).__name__.lower()}", retryable=True)


class ToolGateway:
    def __init__(self, registry: dict[str, ToolDefinition] | None = None, backend: Literal["local", "mcp"] = "local", *, tool_timeout_seconds: float = 3.0, max_output_bytes: int = 20_000, ledger: Any = None):
        self.registry = registry or support_tool_registry()
        self.adapter = LocalToolAdapter() if backend == "local" else MCPToolAdapter()
        self.backend, self.tool_timeout_seconds, self.max_output_bytes, self.ledger = backend, tool_timeout_seconds, max_output_bytes, ledger

    def available_tools(self) -> list[ToolDefinition]:
        return [definition for definition in self.registry.values() if definition.permission == ToolPermission.READ]

    def execute(self, call_id: str, tool_name: str, raw_arguments: dict[str, Any], runtime: ToolRuntime, turn_index: int, retry_count: int = 0) -> ToolResult:
        definition = self.registry.get(tool_name)
        if definition is None:
            return ToolResult(status=ToolStatus.NOT_FOUND, error_code="tool_not_registered")
        if definition.permission != ToolPermission.READ:
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
