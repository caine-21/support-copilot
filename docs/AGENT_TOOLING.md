# Agent Tooling: bounded hybrid workflow

> **Verified baseline**: `c9e1ade chore: pin bounded agent tooling baseline` — clean-room `70 passed`（`git archive c9e1ade` → 全新临时目录 → `py -B -m pytest tests -q`，离线无 API key）。本文件描述 c9e1ade 的真实实现。

`SUPPORT_AGENT_MODE=legacy` keeps the `run_agent` compatibility pipeline. `tool_loop` adds a model-driven, read-only retrieval loop after normalization and the deterministic Risk pre-guard. `SUPPORT_TOOL_BACKEND=local|mcp` selects the protocol adapter; local remains the adapter default and MCP is opt-in. The canonical architecture default is the deterministic `app.runtime.run_a1.run_a1` path; this optional tooling never becomes an authorization source.

**Tool permission**（`agent/tooling.py`, `ToolPermission`）: `read / reversible_write / external_or_irreversible`。当前注册工具全部为 `read`（`search_knowledge_base` / `get_customer_context` / `get_ticket_history`）; code-level 强制（`available_tools()` 只返回 read; `ToolGateway.execute` 非 read → `tool_permission_denied`）。没有 write / side-effect 工具对 agent 开放。

## Boundary

The model can propose a final response and request `search_knowledge_base`, `get_customer_context`, or `get_ticket_history`. It cannot select Risk policy, grounding validation, customer-context authorization, PII handling, or the final `AUTO_REPLY` / `ESCALATE_L1` / `ESCALATE_L2` decision. Those remain deterministic application gates.

Domain Services are shared. LocalFunction and MCP adapters only perform schema validation and result mapping. Every result is a typed `ToolResult(status, data, evidence, error_code, retryable)` with source references.

## Loop and failure policy

The run state stores auditable messages, tool events, evidence, counts and a stop reason—never hidden reasoning or credentials. Limits: turns, tool calls, overall time, per-tool time, duplicate calls and output size. Only read tools can receive bounded retries. Failure, timeout, MCP connection loss, insufficient evidence, or a loop limit can only preserve/escalate the formal decision; it cannot unlock `AUTO_REPLY`.

The gateway emits safe component-level codes such as `tool_not_registered`, `tool_permission_denied`, `invalid_tool_arguments`, `tool_timeout`, `tool_execution_failed`, `mcp_tool_not_found`, `mcp_tool_error`, and `mcp_timeout`; it does not store provider tracebacks in the packet or ledger.

Supported stop reasons include `final_output`, `pre_guard_escalation`, `duplicate_tool_call`, `tool_timeout`, `tool_error`, `max_turns_exceeded`, `max_tool_calls_exceeded`, and `run_timeout_exceeded`. Tool events are appended to the Run Ledger with a call ID, backend, redacted argument shape, evidence references, latency, retry count, and final result status. Raw customer values and chain-of-thought are never ledger fields.

## MCP

Start the local stdio server:

```powershell
py -B -m agent.support_mcp_server
```

It exposes the same read-only domain services through MCP `tools/list` and `tools/call`. The client adapter starts the local process with the official MCP Python SDK, discovers tools, maps structured MCP output back to `ToolResult`, and closes the session/process. It does not connect to CRM, refunds, email, or a remote MCP deployment.

## Reproducible scripted trace

1. Scripted model calls `search_knowledge_base` for an invoice ticket.
2. Gateway validates `query` / `top_k`, invokes Local or MCP, and records `FAQ-billing-01` evidence.
3. Scripted model calls `get_customer_context`.
4. It returns a proposal; deterministic grounding and authorization gates produce the final route.

`tests/test_agent_tooling.py` is no-service and deterministic. Its metrics are orchestration/contract evidence, not real-provider model accuracy.

## Minimal verification

```powershell
# 10 tooling / contract / stdio-MCP tests
py -B -m pytest tests\test_agent_tooling.py -q -p no:cacheprovider
# full clean baseline (70 passed)
py -B -m pytest tests -q
```
