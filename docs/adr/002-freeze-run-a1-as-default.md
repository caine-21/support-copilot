# ADR-002: Freeze `run_a1` as the canonical default architecture

- Status: Accepted
- Date: 2026-08-10
- Scope: architecture classification and default/experimental boundary
- Runtime code change: none

## Context

Support Copilot now contains several verified implementation branches: the deterministic workflow, the A1 request facade, a bounded read-only tool loop, local/MCP tool backends, a read-only Multi-Agent Shadow, and an A5 Manager + Specialists experiment. Treating all of them as peers makes the project harder to explain and obscures which component owns the final authorization decision.

The frozen A5 artifact (`experiments/a5/results/run_a5.json`) gives the relevant comparison on 30 synthetic/de-identified cases:

| Lane | Task success | Model calls/case | P50 latency | Multi-intent |
|---|---:|---:|---:|---:|
| A: deterministic workflow | 0.633 | 0.00 | 656.5 ms | 5/8 |
| C: current Manager + Specialists | 0.633 | 0.73 | 1278.7 ms | 5/8 |

All lanes shared the deterministic authorization gate and recorded zero unsafe AUTO replies. Four malformed ambiguous fixtures failed equally across lanes. Token fields are zero because usage was not instrumented, so they are not cost evidence.

## Decision

The canonical default is the deterministic request workflow exposed by `app.runtime.run_a1.run_a1`:

Intent → Risk Gate → KB Retrieval → Grounding → Authorization → `AUTO_REPLY | ESCALATE_L1 | ESCALATE_L2`

The authorization source remains deterministic. A model may classify, draft, or request a permitted read, but it cannot bypass the risk, grounding, or business authorization gates.

The following remain experimental or optional:

- A5 Lane C model-mediated Manager + Specialists layering: experimental.
- Multi-Agent Shadow: experimental, read-only, and unable to change the formal action.
- Bounded Tool Loop: optional retrieval strategy, never an authorization source.
- MCP runtime/backend: optional protocol adapter behind the existing tool boundary.
- A5 runner and fixtures: experiment infrastructure, not a product runtime.

The A1 codebase contains deterministically selected Knowledge and Support lane modules. Their names do not make A1 a Manager-driven Multi-Agent runtime.

Existing CLI, Gradio, and ticket-service compatibility surfaces still call `run_agent`. They retain the same deterministic policy owner and are not evidence of a competing architecture. New architecture claims and request-level runtime work use `run_a1` as the default.

## Why

Lane C did not beat Lane A on overall task success or multi-intent cases, and it used more model calls with higher median latency. The evidence supports retaining the simpler auditable control flow.

The precise conclusion is: **the current Manager layering did not prove value under the frozen A5 benchmark**. This ADR does not claim that Multi-Agent systems have no value, nor that Lane C represents a complete autonomous Multi-Agent system.

## Consequences

- No new Manager, Sub-Agent, MCP server, tool loop, framework, or runtime is introduced.
- Optional adapters may be exercised for compatibility or protocol tests, but they do not become defaults.
- The malformed ambiguous fixtures are not silently edited under the old benchmark hash. A corrected fixture set requires a versioned benchmark and a full A/B/C rerun.
- Token/cost claims remain unavailable until provider usage metadata is captured; model-call and latency figures are the only current cost proxies.
- Revisit this decision only when a defined failure mode produces comparative evidence that the deterministic workflow cannot address with rules, calibration, retrieval, or data improvements.
