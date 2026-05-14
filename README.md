# Support Copilot — SaaS Ticket Triage Agent

## One-line pitch

An agentic support system that classifies customer tickets, retrieves KB context, drafts replies, and routes to AUTO_REPLY / ESCALATE_L1 / ESCALATE_L2 — with a deterministic safety gate that keeps unsafe auto-reply rate at 0%.

## Problem

SaaS support teams waste capacity on tickets that could be auto-resolved from the knowledge base, while high-churn-risk customers get the same queue as routine how-to questions. A single prompt cannot solve this: it can't retrieve KB context before drafting, detect tone separately from content, or retry with a different strategy when confidence is low.

## Why an Agent

Five tools run in sequence with information flowing between them:

```
classify_intent → kb_search → history_lookup → draft_reply → tone_check
                                                                    ↓
                                              reasoner: confidence + grounding + tone → action
```

`tone_check` results gate the action decision — a frustrated customer with churn signals is never auto-replied regardless of KB coverage. A reflection loop retries `kb_search` with a broader query when confidence is low. Neither of these requires changing the core tools.

## Architecture

```
ticket_in
    ↓
planner.create_plan()        5-step fixed plan
    ↓
agent_loop.run_tool_loop()   dispatch + reflect if confidence < 0.65
    ↓
reasoner.synthesize()        3-rule policy (see below)
    ↓
{intent, priority, tone, kb_grounding, draft_reply, confidence, action, reason}
    ↓
action ∈ {AUTO_REPLY, ESCALATE_L1, ESCALATE_L2}
```

**3-rule routing policy:**

| Rule | Condition | Action |
|---|---|---|
| Churn / SLA | `churn_risk ≥ 0.6` or `(frustrated and churn_risk ≥ 0.4)` or SLA keyword | ESCALATE_L2 |
| Safe auto-reply | `confidence ≥ 0.75` and `grounding == "strong"` (KB score ≥ 0.60) | AUTO_REPLY |
| Everything else | low confidence or weak/no KB | ESCALATE_L1 |

**3-level deterministic grounding** (no LLM self-assessment):

| Level | Condition | Meaning |
|---|---|---|
| `strong` | top KB score ≥ 0.60 | Direct FAQ match — safe to auto-reply |
| `weak`   | top KB score 0.40–0.59 | Related content found — inform L1, don't auto-reply |
| `none`   | top KB score < 0.40 | No coverage — escalate |

## Eval Results

**35 test cases: 20 baseline + 15 adversarial (structured to attack each decision boundary)**

| Metric | Baseline | Adversarial |
|---|---|---|
| Action accuracy | 45% | 73% |
| **L2 recall** | **100%** | **100%** |
| **Unsafe AUTO_REPLY rate** | **0%** | **0%** |
| False escalation rate | 0% | 0% |

Adversarial breakdown by attack type:

| Type | Cases | Passed | What it tests |
|---|---|---|---|
| A — KB misleading | 5 | 3/5 | Strong KB match but answer is plan-tier-specific |
| B — Emotional noise | 5 | 3/5 | Frustration ≠ churn risk (sarcasm, mild frustration) |
| C — Multi-intent | 5 | 5/5 | Mixed intent routing stability |

**Key finding:** adversarial accuracy (73%) exceeds baseline (45%). Failures are concentrated in the baseline set's L2 threshold over-triggering on frustrated-but-low-churn tickets — not edge cases. Multi-intent routing is stable (5/5).

**Safety gates held across all 35 cases:** L2 recall 100%, unsafe auto-reply 0%.

## Stability

- KB search: sentence-transformers cosine similarity (primary) → BM25 keyword fallback
- LLM: DeepSeek (primary) → Groq llama-3.3-70b-versatile fallback via unified `LLMRouter`
- Grounding: deterministic score threshold — does not rely on LLM self-assessment

## Known Limitations (documented, not papered over)

1. **Plan-tier blindness**: grounding checks semantic similarity, not whether the KB answer applies to the user's subscription tier. T-021 (Team plan asking about SSO) and T-024 (version history extension) both fail because strong KB match doesn't guarantee correct answer for the user's context.

2. **Tone classifier on sarcasm**: T-028 ("Oh great, fantastic product") is classified as frustrated + mild churn risk → false L2. Sarcasm detection is not implemented.

3. **context_coverage is unmodeled**: the next production step is adding `(grounding == "strong" AND plan_compatible AND feature_available)` as the AUTO_REPLY gate. This requires user context input to the system.

Evaluation across 35 cases revealed three independent failure manifolds in LLM-based support decisioning: grounding failure (retrieval quality), context failure (entitlement-unaware routing), and tone miscalibration (churn signal false positives). See `notes/failure_taxonomy.md`.

## Quick Start

```bash
cd support-copilot

# single ticket
python -m agent.main --ticket "How do I download my invoice?" --id T-001 --user U-101

# full eval (35 cases, baseline + adversarial)
python -m agent.eval
```

Requires `GROQ_API_KEY` and/or `DEEPSEEK_API_KEY` in `.env`.
