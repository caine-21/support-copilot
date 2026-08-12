---
title: AI Support Triage
emoji: 🎯
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
---

# Support Copilot — SaaS Ticket Routing Decision System

## One-line pitch

Support Copilot is an **A6 operable public prototype** for AI support triage: it classifies SaaS customer tickets, retrieves KB evidence, drafts grounded replies, and decides whether the ticket is eligible for `AUTO_REPLY` or must be routed to `ESCALATE_L1` / `ESCALATE_L2`.

It is not a generic support chatbot. The core question is:

> Under what evidence is an AI system allowed to answer a customer automatically?

## Customer Web Beta

The Render staging service now includes a responsive same-origin customer
portal at `/`. Customers can submit a question without seeing the staging API
token; `POST /customer/tickets` returns only a redacted decision/reply
contract. The portal is deliberately bounded: provider calls and executor
actions remain disabled, and unsupported or weakly grounded questions are
escalated instead of answered with invented detail.

This is a Web beta, not a durable omnichannel helpdesk. Persistent
conversations, operator assignment, tenant isolation, and real WeChat/WeCom
adapters remain the next production gaps. See
[`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md) and
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## A6 operational status

The deployable boundary is `service.operable:app`: authenticated staging mode, separate liveness/readiness/version endpoints, JSON events, W3C trace correlation, Prometheus-format metrics, protected bounded traces, body/concurrency/rate/deadline limits, feature kill switches, atomic action claims, Docker/Render configuration, CI gates, rollback runbook, and a 17-case fault challenge.

Verified in this working branch:

- pre-A6 full offline baseline: `196 passed`; Customer Context Beta `30/30`; Multi-Agent Shadow `20/20` (synthetic/scripted evidence boundaries still apply),
- historical A6 local evidence: `213 passed` (preserved as a historical artifact),
- current full regression: `226 passed`; failure matrix `17/17`; unsafe automatic actions `0`,
- productionization tests: structured error contract, request log fields, release identity fallback, and failure/recovery exercise PASS,
- fault matrix: `17/17`, unsafe automatic actions `0`,
- local staging Uvicorn HTTP smoke: `9/9`,
- local 32-request burst: `32/32`, p95 `230.77ms`, unsafe automatic actions `0`.

The service has a public Render staging deployment at
`https://support-copilot-qiun.onrender.com/`. Release
`38447c2a3e665fd197e524dd8ec905c7423ad763` is live: public liveness,
readiness, version identity, request-ID propagation, structured 404/validation
errors, Chinese FAQ handling, the reproduced Chinese prompt-injection
paraphrase, and honest human-escalation behavior passed on 2026-08-12. The
deploy workflow trigger reached Render successfully, but its readiness wait
still expired during the final Free-tier rollout and skipped the workflow smoke;
direct public HTTP verification passed after the service recovered. This
remains a provider-free, no-send prototype, not a real
support-system integration, high-availability service, or real-model
effectiveness claim.

Operational references: [Operations](docs/OPERATIONS.md), [Runbook](docs/RUNBOOK.md), [Security review](docs/SECURITY_REVIEW.md), [ADR-003](docs/adr/003-a6-operability-stack.md), and [evidence pack](ops/evidence/).

**Canonical facts / reproducibility:** [`./CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) — 唯一事实口径（reproducible test baselines、CURRENT/HISTORICAL eval 标签、复现命令、allowed/forbidden claims）。

## Problem

SaaS support teams waste capacity on routine tickets that could be resolved from the knowledge base, but unsafe automation creates real risk: refund promises, plan-specific feature claims, churn-sensitive customers, SLA/security concerns, and confident replies built on weak KB matches.

This project treats support automation as a routing and safety decision system, not a prompt-writing exercise.

## Architecture

### Default: deterministic `run_a1`

The canonical default is `app.runtime.run_a1.run_a1`: Intent → Risk Gate → KB Retrieval → Grounding → deterministic Authorization → `AUTO_REPLY | ESCALATE_L1 | ESCALATE_L2`. Model output can inform the pipeline but cannot authorize itself. Existing CLI, Gradio, and service compatibility surfaces still call the legacy deterministic implementation; they are not a second architecture authority.

Tool Loop and MCP are optional adapters. Manager + Specialists (A5 Lane C), Multi-Agent Shadow, and the A5 harness are experimental. See [ADR-002](docs/adr/002-freeze-run-a1-as-default.md).

### Experimental: Multi-Agent Shadow (offline-evaluated)

Multi-Agent Shadow is an offline-evaluated advisory layer with an independent Support Manager, Billing Specialist, Technical Specialist, domain-isolated ticket slices, explicit KB domains, deterministic merging, safe component errors, and a data-driven three-layer Oracle. Shadow does not change the formal routing or auto-reply authorization decision.

Run its scripted/fake harness locally:

```powershell
py -B -m agent.multi_agent_eval
```

Current offline result: Scenario `20/20`, Manager Accuracy `0.90`, Multi-intent Coverage `0.80`, and Off/Shadow Unsafe AUTO_REPLY `0/0` (delta `0`). These are not real-model effectiveness or production-validation claims. See [Multi-Agent Shadow documentation](docs/MULTI_AGENT_SHADOW.md) for architecture, Eval semantics, and the evidence boundary.

The separate A5 A/B/C experiment found Lane A workflow and Lane C Manager layering both at task success `0.633`; Lane C had higher P50 latency (`1278.7ms` vs `656.5ms`), more model calls (`0.73` vs `0.0` per case), and the same multi-intent result (`5/8`). The bounded conclusion is: **the current Manager layering did not prove value in this benchmark**. It is not evidence that Multi-Agent systems have no value in general.

```
ticket_in
  -> synthetic customer_context fixture (Beta; no CRM)
  -> phase 1: classify_intent | kb_search | history_lookup | tone_check
  -> deterministic early-L2 gate for SLA / hidden-cancel / security-like signals
  -> draft_reply
  -> grounding_compiler
  -> reasoner.synthesize()
  -> AUTO_REPLY | ESCALATE_L1 | ESCALATE_L2
```

Phase 1 runs independent signal gathering in parallel. Generation and verification stay sequential because the draft must be checked against the KB before any autonomous reply is allowed.

## What makes it different from a chatbot

### 1. Deterministic grounding gate

`AUTO_REPLY` is not controlled by the model's self-reported confidence. The system checks KB grounding explicitly:

**3-level deterministic grounding** (no LLM self-assessment):

| Level | Condition | Meaning |
|---|---|---|
| `strong` | top KB score ≥ 0.60 | Direct FAQ match — safe to auto-reply |
| `weak`   | top KB score 0.40–0.59 | Related content found — inform L1, don't auto-reply |
| `none`   | top KB score < 0.40 | No coverage — escalate |

### 2. Intent Normalization Layer (INL)

Raw ticket text is compiled into a stable `intent_set` before retrieval. Known intents map to FAQ entries deterministically; embeddings and BM25 are fallback paths for unknown intents.

This keeps common routing decisions stable instead of relying entirely on vector similarity.

### 3. Context guard

The system separates:

- LLM extraction: infer user context such as plan / region when present.
- Rule enforcement: block auto-reply when the KB answer may not apply to that user's entitlement.

This is the current guard against plan-tier and region-specific false-safe answers.

### 4. Grounding compiler

The draft reply is decomposed into factual claims. Each claim is checked against the retrieved KB snippets. If the draft exceeds the KB boundary, `AUTO_REPLY` is downgraded to `ESCALATE_L1`.

Grounding authorization is fail-closed: missing, empty, malformed, or failed evidence checks cannot unlock `AUTO_REPLY`; valid strong grounding remains eligible (commit `2c13496`). See [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §6③.

### 5. Append-only run ledger

Each eval run can write immutable artifacts under `data/runs/<run_id>/`:

- `meta.json`
- `steps.jsonl`
- `outputs.jsonl`
- `decisions.jsonl`
- derived `report.json`

The ledger records what happened. Metrics and pass/fail judgments are derived views, not permanent facts.

### 6. Assumption trace and replay

The reasoner separates deterministic facts from LLM-inferred assumptions such as churn risk, tone, and intent confidence.

`assumption_replay` asks: if a model assumption were neutralized, would the action change? This identifies decisions that are fact-grounded versus assumption-driven.

## Reproducible test baseline

Commit-pinned milestones remain recorded in [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §2. The current `dd7ca87` runtime/test files plus this docs-only architecture-freeze diff passed the full offline suite: **196 passed in 242.61s** on 2026-08-10. This is a HEAD-equivalent runtime regression, not a new clean-room commit claim.

## A1 Unified Request Runtime (`app/`)

An additive domain facade over the verified `agent.*` modules: unified `IncomingRequest` → deterministic `Request Router` (channel / intent / risk / context) → `ContextProjection` → Support / Knowledge Specialist lanes → existing grounding + risk + authorization gate → structured trace. `app/` owns contract, coordination, projection, routing and trace — never policy.

Honest channel boundary: **ticket = SUPPORTED** (full vertical slice); **email / lead = ROUTING_ONLY** (contract + route only, no specialist, no side effect). It is not a three-channel agent. Demo cases and traces: `data/a1_demo_cases.json`; evidence pack: `notes/interview-prep/flagship-projects/a1/`. See [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §6④.

## MCP tool boundary

Four typed read tools (`search_knowledge_base` / `get_customer_context` / `get_ticket` / `get_ticket_history`) run on either a Local or a real stdio MCP backend with identical business semantics; the A1 Knowledge Specialist uses an injected scoped gateway and never sees the transport. Specialists are capability-withheld: Knowledge sees only `search_knowledge_base`; the server additionally exposes one `EXTERNAL_OR_IRREVERSIBLE` action — `execute_approved_reply(ticket_id)` — which is executor-only and reads persisted human approval, evidence and idempotency (a caller cannot pass approval or reply text). All external effects remain mock (`MockTicketActionAdapter`, `sent_mock`). See [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §6⑤.

## Skills

A Skill is not a tool, not a Specialist, and not a policy — it is a typed, deterministically selected capability package (Prompt/Context/Tool/Policy composition). One skill is currently implemented (`knowledge_lookup`, a deterministic read skill). Selection is deterministic by specialist + intent; skill context is a minimal subset of the Specialist projection, and tool capability is the intersection of Specialist scope and Skill allowed tools (registration and runtime both reject any widening). Skills can never expand capability or grant authorization. See [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §6⑥.

## HITL / review checkpoint (ticket-only)

Proposal → persisted review checkpoint (WAITING_FOR_REVIEW) → human approve / edit / reject → bound approved payload + SHA-256 hash (READY_FOR_EXECUTION) → explicit resume/executor → mock action. **Approval and execution are separated**: `review_ticket(approved)` never executes; only the executor (`execute_approved_reply(ticket_id)`) does, after revalidating review state, approved-content integrity, evidence and idempotency. The checkpoint is SQLite-persisted and survives a new service instance. Ticket-only — email/lead remain ROUTING_ONLY. See [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §6⑦.

## Historical model-evaluation snapshot (HISTORICAL)

> ⚠️ The table below is a **historical model-evaluation artifact** (`data/reports/report_epistemic-r3.json`): it requires a real provider API key, is non-deterministic, and was **not re-run** as part of the `c9e1ade` clean committed baseline. Cite it as a historical snapshot, not as the current committed result.

Latest checked report: `data/reports/report_epistemic-r3.json`.

| Metric | Result |
|---|---:|
| Total eval cases | 100 |
| Passed cases | 95 / 100 |
| Action accuracy | 96% |
| L2 recall | 100% |
| Unsafe AUTO_REPLY rate | 0% |
| AUTO_REPLY decisions held up only by LLM assumptions | 0 |

Dataset shape:

- 85 baseline / adapted cases
- 15 adversarial cases
- Expected actions: 24 `AUTO_REPLY`, 45 `ESCALATE_L1`, 31 `ESCALATE_L2`

The key safety result is not raw accuracy. The main invariants are:

- **L2 recall must stay 100%**: high-risk tickets cannot be missed.
- **Unsafe AUTO_REPLY must stay 0%**: no auto-reply without strong grounding.

Deterministic / scripted evaluations that **are** reproducible (no provider): Customer Context Beta `30/30` (provider none, commit `efea70b`) and Multi-Agent Shadow `20/20` (offline scripted). See [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §6.

## Stability

- KB search: INL intent-to-FAQ lookup first; hybrid dense + BM25 fallback for unknown intents
- LLM: DeepSeek (primary) → Groq llama-3.3-70b-versatile fallback via unified `LLMRouter`
- Grounding: deterministic score threshold plus claim-level grounding compiler
- Run evidence: append-only run ledger and structured JSON reports

## Key files

| File | Purpose |
|---|---|
| `agent/agent_loop.py` | Orchestrates parallel signal gathering, early-L2 gate, generation, grounding, and replay attachment |
| `agent/reasoner.py` | Final routing policy, safety gates, assumption trace/replay |
| `agent/intent_normalizer.py` | INL: text -> stable intent set |
| `agent/kb.py` | Intent-to-FAQ lookup plus hybrid retrieval fallback |
| `agent/context_guard.py` | Plan/region entitlement guard |
| `agent/customer_context.py` | Structured customer-field validation and AUTO_REPLY gate |
| `agent/customer_context_eval.py` | Frozen 30-case deterministic no-service evaluation entry |
| `agent/grounding_compiler.py` | Claim-level KB support check for draft replies |
| `agent/eval.py` | 100-case eval runner and report writer |
| `agent/run_ledger.py` | Append-only run ledger |
| `data/query_assumptions.py` | Query assumption-driven decisions from a report |
| `SHOWCASE.md` | Three readable case walkthroughs for interview/demo use |

## Known Limitations (documented, not papered over)

This project is an operable, locally verified beta, not a production system. It demonstrates the decision flow, evaluation loop, protected service boundary, and release/rollback evidence without a real customer-service integration or a verified hosted staging instance.

1. **No real customer system integration**  
   There is no Zendesk / Intercom / Freshdesk adapter. Tickets are provided through CLI, Gradio, or eval fixtures.

2. **Customer context is local and synthetic**
   The Beta now accepts structured plan, region, role, permissions, contract, and account fields, but only through synthetic fixtures. There is no CRM adapter, real customer data, or independent support-agent review.

3. **KB annotations are partly hard-coded**  
   Plan-dependent rules live in guard code. A more realistic implementation would annotate each FAQ with `min_plan`, `regions`, `requires_csm`, and risk level.

4. **Tone and churn inference still use LLM signals**  
   Deterministic L2 signals cover SLA and hidden-cancel patterns, but some churn decisions remain assumption-driven and are tracked by assumption replay.

5. **Review-gated feedback candidate loop only**
   Failures can be sanitized into `pending_human_review` candidates, but no human agent correction is automatically promoted into the eval dataset or policy.

6. **Demo UI is explanatory, not an agent console**  
   The Gradio app is for interview/demo inspection. It is not a full support dashboard.

7. **Single-instance staging state and telemetry**
   SQLite, rate limits, metrics, and trace retention are process-local. Render free-tier disk is ephemeral; there is no distributed exactly-once or durable observability claim.

8. **Provider and retry boundary**
   Provider mode performs one primary attempt and at most one fallback attempt. Same-provider exponential-backoff retries are deliberately not automatic in A6 to cap duplicate egress and cost.

## Quick Start

### A6 service (provider-free local demo)

```powershell
$env:SUPPORT_DEPLOYMENT_MODE='demo'
$env:ENABLE_PROVIDER_CALLS='false'
$env:ENABLE_PUBLIC_DEMO='true'
$env:ENABLE_EXECUTOR='false'
py -B -m uvicorn service.operable:app --host 127.0.0.1 --port 7860 --no-access-log
```

Then inspect `/livez`, `/readyz`, and `/version`. For staging auth and smoke commands, use [docs/OPERATIONS.md](docs/OPERATIONS.md).

### Bounded agent tooling (local / no-service test harness)

The canonical default is the deterministic `run_a1` architecture. The optional tool loop uses native provider function calls in production and a scripted adapter in tests; MCP remains an optional backend. Risk, grounding and authorization remain deterministic gates. See [Agent Tooling](docs/AGENT_TOOLING.md).

```powershell
$env:SUPPORT_AGENT_MODE="tool_loop"
$env:SUPPORT_TOOL_BACKEND="local" # or mcp
py -B -m pytest tests\test_agent_tooling.py -q -p no:cacheprovider
```

Use `py` on Windows.

```powershell
cd D:\ehe\support-copilot
py -m pip install -r requirements.txt
```

Configure at least one provider key in `.env`:

```text
DEEPSEEK_API_KEY=...
GROQ_API_KEY=...
```

Single ticket:

```powershell
py -m agent.main --ticket "How do I download my invoice?" --id T-demo --user U-demo
```

Gradio demo:

```powershell
py app.py
```

Full eval:

```powershell
py -m agent.eval latest
```

Customer Context Beta deterministic evaluation (no provider):

```powershell
py -m agent.customer_context_eval --dataset-version v2 --tag <new-tag>
```

This writes a new report and run ledger. Do not run full eval unless you want new artifacts under `data/reports/` and `data/runs/`.

Query assumption-driven decisions from an existing report:

```powershell
py data/query_assumptions.py epistemic-r3 --action AUTO_REPLY --highrisk
```

## Demo / Eval Review

For a portfolio or interview walkthrough:

- Run the demo with `py app.py`, then open the local Gradio URL printed in the terminal.
- Run a new eval with `py -m agent.eval <tag>`. This creates a new report and run ledger.
- Inspect the latest checked report at `data/reports/report_epistemic-r3.json`.
- Read `SHOWCASE.md` for three representative decisions: safe auto-reply, L1 review, and L2 escalation.

## Interview framing

The project demonstrates AI agent landing skills beyond prompt tuning:

- defining when automation is allowed,
- separating model assumptions from verified facts,
- designing evals around safety invariants,
- making failures visible through reports and ledgers,
- documenting known blind spots instead of hiding them.

The shortest summary:

> I built a support automation risk gate. It shows when AI can safely auto-reply, when it must route to human review, and what evidence supports that decision.
