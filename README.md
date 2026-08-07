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

Support Copilot is an offline-evaluated AI support triage POC: it classifies SaaS customer tickets, retrieves KB evidence, drafts grounded replies, and decides whether the ticket is eligible for `AUTO_REPLY` or must be routed to `ESCALATE_L1` / `ESCALATE_L2`.

It is not a generic support chatbot. The core question is:

> Under what evidence is an AI system allowed to answer a customer automatically?

**Canonical facts / reproducibility:** [`./CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) — 唯一事实口径（reproducible test baselines、CURRENT/HISTORICAL eval 标签、复现命令、allowed/forbidden claims）。

## Problem

SaaS support teams waste capacity on routine tickets that could be resolved from the knowledge base, but unsafe automation creates real risk: refund promises, plan-specific feature claims, churn-sensitive customers, SLA/security concerns, and confident replies built on weak KB matches.

This project treats support automation as a routing and safety decision system, not a prompt-writing exercise.

## Architecture

### Multi-Agent Shadow (offline-evaluated)

Multi-Agent Shadow is an offline-evaluated advisory layer with an independent Support Manager, Billing Specialist, Technical Specialist, domain-isolated ticket slices, explicit KB domains, deterministic merging, safe component errors, and a data-driven three-layer Oracle. Shadow does not change the formal routing or auto-reply authorization decision.

Run its scripted/fake harness locally:

```powershell
py -B -m agent.multi_agent_eval
```

Current offline result: Scenario `20/20`, Manager Accuracy `0.90`, Multi-intent Coverage `0.80`, and Off/Shadow Unsafe AUTO_REPLY `0/0` (delta `0`). These are not real-model effectiveness or production-validation claims. See [Multi-Agent Shadow documentation](docs/MULTI_AGENT_SHADOW.md) for architecture, Eval semantics, and the evidence boundary.

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

## Reproducible test baseline (current clean)

Bounded agent tooling is committed at `c9e1ade`; clean-room verification (`git archive <commit>` → temp → offline pytest) gives **70 passed** (60 legacy/service + 10 tooling). Current clean baseline is **113 passed** at `2429c63` (A1 unified runtime). See [`CANONICAL_FACTS.md`](./CANONICAL_FACTS.md) §2 for the baseline table.

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

This project is an offline-evaluated POC, not a production system. It demonstrates the decision flow and evaluation loop without a real customer-service integration.

1. **No real customer system integration**  
   There is no Zendesk / Intercom / Freshdesk adapter. Tickets are provided through CLI, Gradio, or eval fixtures.

2. **Customer context is local and synthetic**
   The Beta now accepts structured plan, region, role, permissions, contract, and account fields, but only through synthetic fixtures. There is no CRM adapter, real customer data, or independent support-agent review.

3. **KB annotations are partly hard-coded**  
   Plan-dependent rules live in guard code. A more realistic implementation would annotate each FAQ with `min_plan`, `regions`, `requires_csm`, and risk level.

4. **Tone and churn inference still use LLM signals**  
   Deterministic L2 signals cover SLA and hidden-cancel patterns, but some churn decisions remain assumption-driven and are tracked by assumption replay.

5. **No online feedback loop**  
   Human agent corrections do not yet feed back into the eval dataset or policy worklist.

6. **Demo UI is explanatory, not an agent console**  
   The Gradio app is for interview/demo inspection. It is not a full support dashboard.

## Quick Start

### Bounded agent tooling (local / no-service test harness)

The default remains the Legacy safety workflow. The optional tool loop uses native provider function calls in production and a scripted adapter in tests; Risk, grounding and authorization remain deterministic gates. See [Agent Tooling](docs/AGENT_TOOLING.md).

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
