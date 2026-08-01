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

## Current eval snapshot

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
