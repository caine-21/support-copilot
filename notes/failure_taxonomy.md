# Failure Taxonomy — Support Copilot Decision System

This document maps the failure geometry of the triage system across 35 evaluated cases.
It is an evaluation artifact, not a design log — see `design.md` for architecture rationale.

---

## Decision Boundary Space

The system makes decisions across three independent axes:

```
                      ↑ churn_risk / tone signal
                      │
          L2 zone     │     L2 zone
          (tone weak) │     (churn real)
                      │
  ──────────────────[F3]──────────────────→ grounding strength
                      │         ↗
       L1 zone        │   [F2] false-safe zone
       (weak/none)    │       AUTO_REPLY zone
                [F1]  │
                      ↓ confidence
```

Three failure manifolds (F1, F2, F3) correspond to breakdowns at different locations
in this space. Each is structurally independent — fixing one does not fix the others.

---

## Manifold F1 — Grounding Failure

**Definition:** The KB contains a topically relevant document, but embedding similarity
falls below the strong-grounding threshold (< 0.60). The system correctly routes to L1,
but for the wrong reason — it treats a coverage gap as a confidence gap.

**Location in space:** Left side — low grounding score despite correct intent detection.

**Failure cases:**
- T-021: User on Team plan asks about SSO setup. FAQ-security-01 covers SSO but scores
  weak (embedding similarity 0.40–0.59). Routes to ESCALATE_L1. Correct outcome,
  wrong mechanism — the block is grounding, not the entitlement guard.
- T-024: User asks about extending version history. FAQ-feature-07 covers the topic but
  scores below threshold. Same outcome as T-021.

**Detection signal:** `grounding=weak` on tickets where topic intent is unambiguous and
a relevant FAQ exists. Distinguishable from true coverage gaps by inspecting `kb_results`
— weak score with high semantic relevance indicates embedding model mismatch, not absence.

**Mitigation hypothesis:** Hybrid retrieval (dense + BM25) with reciprocal rank fusion
would raise recall on these cases without changing the policy threshold. The fix is in
retrieval quality, not routing logic.

---

## Manifold F2 — Context Failure

**Definition:** Grounding is strong (score ≥ 0.60) and the FAQ is genuinely relevant,
but the answer is plan-tier-specific. The system may auto-reply with a correct-sounding
but wrong-for-this-user answer. This is the most dangerous failure mode — high confidence
on a wrong answer.

**Location in space:** The false-safe zone — strong grounding + high confidence, but
context_coverage is unverified.

**Failure cases:**
- T-009: Enterprise user asks about VAT invoice. FAQ-billing-04 (strong match) contains
  the caveat "requires CSM for custom invoices." System routes correctly — but only
  because the FAQ text happens to encode the plan constraint. This is a lucky pass,
  not a reliable one.
- T-022, T-023: context_guard v2 catches these — plan extracted as "team", KB entry
  in `_ENTERPRISE_ONLY` → blocked before AUTO_REPLY. Guard working as designed.
- Unguarded gap: any FAQ that is plan-specific but doesn't appear in `_ENTERPRISE_ONLY`
  or `_PLAN_DEPENDENT`. The guard's coverage depends on a manually maintained dict —
  if a new FAQ is added to the KB without a corresponding guard entry, F2 is invisible.

**Detection signal:** `guard["flag"] == "plan_mismatch"` or `"plan_unknown"` catches
the enumerated cases. Unenumerated cases have no signal — they appear as clean AUTO_REPLY.
The absence of a signal is not evidence of safety.

**Mitigation hypothesis:** Replace the hard-coded entitlement dict with a structured
KB annotation layer — each FAQ document carries `min_plan`, `regions`, `requires_csm`
fields. Guard reads annotations instead of maintaining a parallel list. Coverage
becomes a property of the KB, not the guard.

---

## Manifold F3 — Tone Miscalibration

**Definition:** The tone classifier misreads the emotional signal, causing the routing
decision to misfire on the churn_risk axis. Two sub-types:

**F3a — False positive (over-escalation):** Surface frustration language triggers L2
churn logic when churn intent is absent. Most common failure in the baseline set.

**F3b — False negative (under-detection):** Sarcasm or ironic phrasing presents as
positive/neutral, masking genuine frustration.

**Location in space:** Vertical misalignment — correct grounding and confidence, but
churn_risk signal is wrong, shifting the decision up or down the tone axis incorrectly.

**Failure cases (F3a — over-escalation):**
- T-006, T-008, T-011, T-015, T-017, T-018: Baseline cases with frustrated tone but
  no actual churn intent. All routed to L2 (churn logic triggered). Expected: L1 or
  AUTO_REPLY. These account for the majority of baseline accuracy failures (45%).

**Failure cases (F3b — sarcasm):**
- T-028: "Oh great, fantastic product — can't export anything." Classified as frustrated
  + mild churn risk → false L2. Sarcasm inverts the sentiment polarity; the classifier
  reads it as genuine frustration.

**Detection signal:** `churn_risk` score elevated without `churn_signals` containing
explicit intent phrases (e.g., "cancel", "switching", "refund", "leaving"). High
churn_risk with empty or weak churn_signals is an F3a indicator.

**Mitigation hypothesis:** Two-stage tone classification — first detect sentiment
polarity (frustrated / neutral / positive), then separately classify churn intent
(explicit cancellation / implicit dissatisfaction / no churn signal). Churn escalation
should require both elevated sentiment AND explicit intent signals, not either alone.
Sarcasm detection requires semantic context models, not keyword scoring.

---

## Cross-Manifold Summary

| Manifold | Failure mode | System layer | Cases affected | Safety risk |
|---|---|---|---|---|
| F1 — Grounding | Weak similarity on relevant FAQ | KB retrieval | T-021, T-024 | Low — routes to L1 safely |
| F2 — Context | Strong match, wrong plan/region answer | context_guard | T-022/T-023 (caught); unenumerated (undetected) | High — invisible false safe |
| F3 — Tone | Churn signal miscalibration | tone_check + reasoner | T-006/T-008/T-011/T-015/T-017/T-018/T-028 | Medium — over-escalation, one sarcasm false L2 |

**Key structural insight:** F1 and F3 failures are visible — the system routes them
elsewhere (L1/L2) and they show up as accuracy misses. F2 is the dangerous one:
a clean AUTO_REPLY with no signal that the answer was wrong for this user's context.
Safety engineering should prioritize eliminating invisible failures over improving
accuracy on visible ones.

---

## Failure Space Map (Detectability × Impact)

To unify F1 / F2 / F3, we map all three failure modes into a 2D space:

- X-axis: **Detectability** — how easily the failure surfaces in existing evaluation
- Y-axis: **Impact** — how costly the failure is in production

```
              HIGH IMPACT
                   ↑
                   │
     F2            │
 (silent           │   ← highest-risk class
  false-safe)      │     invisible under action oracle
  plan/region/     │     requires new eval design
  role ambiguity   │
                   │
                   │
     F3            │
 (tone             │
  miscalibration,  │
  false L2 spikes) │
                   │
                   │
     F1            │
 (retrieval        │
  noise)           │
                   │
                   └──────────────────────────→ DETECTABILITY
                       low                high
```

**F1 — low impact, high detectability:**
Visible in logs (grounding=weak). Routes safely to L1 — no wrong answer reaches user.
Fix is in retrieval quality (hybrid BM25 + dense), not policy logic.

**F3 — medium impact, medium detectability:**
Shows up as false L2 spikes in the eval summary. Accuracy loss is visible and countable.
Fix is in tone classification (sentiment ≠ churn intent), not routing thresholds.

**F2 — high impact, low detectability:**
Does not appear in the action-based oracle. System routes to AUTO_REPLY with high
confidence and no error signal. The failure is only detectable by comparing the reply
to ground-truth user context — which the current eval does not have.
Fix requires new evaluation design (F2 benchmark + safe_wrong_answer_rate), not model tuning.

**Core insight:** F2 is not a model failure. It is an evaluation blind spot.

The system is not optimized for correctness in the abstract — it is optimized for
*detectable failure reduction under a limited oracle*. The oracle boundary is the real
engineering constraint. Improving accuracy on F1 and F3 is optimization within the
current eval scope. Addressing F2 requires expanding the eval scope itself.

---

## What This System Demonstrates

This failure taxonomy is the artifact that distinguishes evaluation engineering from
benchmark chasing. The system's 45% baseline accuracy is not a failure to be optimized
away — it is a map of where the decision boundary breaks down and why. Each failure
manifold has a different root cause, a different detection strategy, and a different
fix. Treating them as a single "accuracy" number would obscure all of that structure.
