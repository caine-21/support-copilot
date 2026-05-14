# Design Decisions — Support Copilot

## Why an agent instead of a single prompt

A single "classify + draft" prompt cannot handle the three failure modes this system is designed for:

**1. KB grounding before drafting.** A single prompt hallucinates when KB is not retrieved first. The draft_reply tool receives kb_snippets as input — it cannot invent content it was never given.

**2. Tone-gated routing.** The same question ("refund please") triggers different actions depending on tone. Detecting tone as a separate signal — not embedded in the reply prompt — lets the reasoner apply the churn rule cleanly without the LLM conflating emotional state with answer quality.

**3. Reflection on low confidence.** When intent is ambiguous or KB returns no strong match, the system retries with a broader query. A single prompt cannot retry with a different strategy.

---

## Grounding: why deterministic, not LLM-assessed

Early versions used `draft.get("grounded")` — the LLM's self-assessment of whether the reply was supported. This was the largest source of policy failures:

- LLM self-reported `grounded: true` on partial matches (T-009, T-019)
- LLM self-reported `grounded: false` on strong matches (caused false ESCALATE_L1 on T-004, T-005)

**Fix:** grounding is now deterministic — `top_score >= 0.60` for "strong", `>= 0.40` for "weak", below for "none". The LLM cannot override this signal.

**Why 0.60 for strong?** Empirically calibrated on the 20-case baseline. At 0.40 (previous threshold), cases with tangential KB matches (SAP integration against webhook FAQ) were rated as grounded. At 0.60, only direct semantic matches qualify.

---

## Three-tier action design

| Action | Condition | Reasoning |
|---|---|---|
| AUTO_REPLY | confidence ≥ 0.75 AND grounding == "strong" | Both signal AND evidence required |
| ESCALATE_L1 | confidence < 0.75 OR grounding ≠ "strong" | Safe fallback — over-routing to L1 costs agent time, not customer trust |
| ESCALATE_L2 | churn_risk ≥ 0.6 OR (frustrated AND churn_risk ≥ 0.4) OR SLA keyword | Automation on a churn-risk customer accelerates churn |

**Risk asymmetry is intentional.** AUTO_REPLY is irreversible — a wrong auto-reply erodes trust and cannot be unsent. L1/L2 escalation is always recoverable. The system biases toward escalation under uncertainty.

---

## Adversarial eval: what we found

After building the baseline 20-case eval, 15 adversarial cases were added — designed to attack each decision boundary, not just test harder inputs.

**A-type (KB misleading, 3/5 passed):**
The two failures (T-021, T-024) did not reach context_guard. Diagnostic: both returned `grounding=weak` (KB score 0.40–0.59) → ESCALATE_L1 before the entitlement check runs. This is a correct routing outcome — weak grounding already prevents unsafe AUTO_REPLY — but it means context_guard's plan-tier rules were never exercised on these cases. The actual context_guard validation coverage in the adversarial set is T-022 and T-023 (both passed: correct plan-mismatch blocks).

The remaining unsolved A-type problem: if a plan-tier-specific FAQ scores above 0.60 (strong), the system will AUTO_REPLY through context_guard only if the user's plan is identifiable from the ticket. If plan is `unknown` and the KB entry is in `_PLAN_DEPENDENT`, context_guard blocks correctly. If plan is `team` and the KB entry is in `_ENTERPRISE_ONLY`, context_guard blocks correctly. The gap is cases where the KB text implies the right answer but doesn't contain explicit plan language — context_guard can't detect that.

**B-type (Emotional noise, 3/5 passed):**
T-028 (sarcasm: "Oh great, fantastic product") is misclassified as frustrated + mild churn risk → false L2. T-029 (mild acknowledged frustration) routed correctly after reasoner threshold calibration. The tone classifier detects surface-level sentiment signals without semantic context — sarcasm detection is not implemented.

**C-type (Multi-intent, 5/5 passed):**
All five multi-intent cases routed correctly. The system correctly escalated when churn intent was present in a mixed ticket (T-033: export + cancel), correctly triggered L2 on SLA keyword even without explicit frustration (T-032), and correctly avoided AUTO_REPLY on 3-intent tickets (T-034).

**Key finding:** adversarial accuracy (73%) is higher than baseline accuracy (45%). This means the system's failures are concentrated in a specific pattern — L2 threshold over-triggering on frustrated-but-low-churn tickets in the baseline set — not in adversarial edge cases. The system is more brittle on common patterns than on designed attacks.

---

## Known limitation: context_coverage is unmodeled

The current grounding check answers: "Is there a semantically similar FAQ?"

It does not answer: "Does this FAQ apply to this user's plan, region, or entitlement?"

The T-009 case (enterprise VAT invoice) illustrates this: KB-billing-04 has a strong match and the answer is correct (enterprise requires CSM). But this only works because the FAQ text happens to contain the enterprise caveat. If the FAQ were written differently — or if the question were about a feature that exists in the KB for Team but not for a specific region — the system would give a wrong answer with high confidence.

The correct fix is not adding complexity to the current system. It requires a user context input layer:

```
SAFE_TO_AUTO_REPLY = (
    grounding == "strong"
    AND plan_compatible(user.plan, kb_entry.min_plan)
    AND feature_available(user.region, kb_entry.regions)
)
```

This is a production v2 problem. The current system documents the gap rather than pretending it doesn't exist.

---

## LLM abstraction: why LLMRouter matters

The original implementation used direct Groq API calls with `llama-3.1-70b-versatile`. During development, this model was decommissioned mid-session — the entire pipeline failed silently until the error surfaced in tool output.

`LLMRouter` fixes this at the architecture level: both providers (DeepSeek via OpenAI-compatible API, Groq) use the same `openai.OpenAI` client pointed at different base URLs. Adding a new provider is one method + one entry in the provider list. The router tries providers in order and logs which one was used.

This is not over-engineering — it's the direct response to a failure that happened during this project.

---

## What this system demonstrates (and what it doesn't)

**Demonstrates:**
- Eval-driven policy iteration: threshold and rule changes were driven by specific failure cases, not intuition
- Safety metric design: `unsafe_auto_reply_rate` and `L2 recall` are the primary gauges, not accuracy
- Structured adversarial testing: failures were clustered by attack type to identify root causes
- Honest engineering: known limitations are documented, not patched with workarounds

**Does not demonstrate:**
- Production-grade context-aware policy (plan/tier/region checks)
- Sarcasm-robust tone classification
- Online learning or feedback loops
- Persistent memory across sessions
