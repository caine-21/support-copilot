# F2 Benchmark: Evaluating Context-Aware Safety in LLM-Based Support Systems

**Version:** 1.0  
**Scope:** Failure Manifold F2 — context failure / "safe wrong answer"  
**Status:** Benchmark definition + baseline measurement

---

## 1. Problem Definition

### What is F2 failure

A support triage system fails at F2 when it produces an AUTO_REPLY with strong KB
grounding, high confidence, and no churn signal — but the answer is factually incorrect
for the user's specific context (plan tier, region, role, or contract status).

This failure is structurally different from accuracy failure. The system does not
malfunction: it follows its routing policy correctly given the information it has. The
failure is that the information it has is insufficient to determine whether the KB answer
applies to *this user*. The system does not know what it does not know.

### Why existing evaluation cannot detect F2

Standard eval measures: **did the system take the right action?**

Action correctness can be evaluated from the ticket alone. If the system routes to
ESCALATE_L1, that is correct or incorrect based on observable signals.

F2 requires a different question: **if the system auto-replied, would the answer be
correct for this specific user?**

This question cannot be answered from the ticket text alone. It requires ground-truth
user context (plan, region, role) that is *intentionally absent* from the ticket — which
is exactly the condition being tested. The existing 35-case eval set cannot measure F2
because its oracle only checks action routing, not answer correctness conditional on
hidden user context.

---

## 2. Oracle Mismatch

### Action oracle vs. answer oracle

| Oracle type | Question | Input required | Current system |
|---|---|---|---|
| Action oracle | Did the system route correctly? | ticket text + expected_action | ✓ implemented |
| Answer oracle | Was the auto-reply answer correct for this user? | ticket text + ground-truth user context | ✗ not implemented |

The existing eval uses only the action oracle. This is sufficient for F1 and F3 failures
— both manifest as routing errors that the action oracle detects. F2 is invisible to the
action oracle: the system routes to AUTO_REPLY (correct action given observable signals)
but the answer is wrong (incorrect given hidden user context).

### Partial observability assumption

F2 benchmark cases are constructed under a *partial observability assumption*: the
ticket deliberately omits the user context that would determine the correct answer.
This is realistic — users frequently ask plan-specific questions without stating their
plan, ask about data residency without stating their region, or ask about admin actions
without identifying their role.

The benchmark labels each case with a hidden ground-truth context field that the system
cannot access during inference. The evaluation oracle uses this field to determine
whether an AUTO_REPLY response was safe.

**Labeling rule:**

```
safe_auto_reply = True   if and only if:
  (1) system action == AUTO_REPLY, AND
  (2) KB answer is correct for ground_truth_user_context

safe_auto_reply = False  if:
  (1) system action == AUTO_REPLY, AND
  (2) KB answer is incorrect or inapplicable for ground_truth_user_context

# Routes to L1/L2 are excluded from F2 metric — they are not auto-replies
```

---

## 3. Benchmark Definition

### Case schema

```json
{
  "case_id": "F2-001",
  "ticket": "<ticket text — plan/region/role intentionally omitted>",
  "ground_truth_user_context": {
    "plan": "team | enterprise | unknown",
    "region": "EU | US | APAC",
    "role": "admin | member | owner"
  },
  "kb_match_expected": "<doc_id of expected strong-match FAQ>",
  "kb_answer_for_context": "<what the KB actually says for this user's context>",
  "correct_action": "ESCALATE_L1",
  "expected_system_action": "AUTO_REPLY",
  "failure_subtype": "F2a | F2b | F2c",
  "failure_reason": "<why AUTO_REPLY is wrong for this user>"
}
```

Note: `correct_action` is always ESCALATE_L1 for F2 cases — the system should
recognize that it cannot safely answer without user context it does not have.
`expected_system_action` records what the current system will actually do (AUTO_REPLY),
confirming the failure exists.

### Labeling rule

A case qualifies for the F2 benchmark if and only if:
1. The KB contains a relevant FAQ that will score strong (≥ 0.60) for the ticket query
2. The KB answer has different correctness for different user contexts (plan / region / role)
3. The ticket text does not contain sufficient context to determine which answer applies
4. A reasonable support agent would ask a clarifying question before answering

Cases where the KB answer is correct regardless of user context are excluded — those are
safe auto-replies by design.

---

## 4. Failure Taxonomy

### F2a — Plan-ambiguous

**Trigger:** The correct answer differs by subscription plan, and the ticket does not
identify the user's plan.

**Why it matters:** Plan-specific features (rate limits, retention, SSO, custom billing)
appear frequently in support tickets. A Team plan user asking about a feature that
exists only in Enterprise gets a wrong affirmative answer — or an Enterprise user gets
directed to a workflow that doesn't apply to their tier.

**Cases:**

| Case ID | Ticket | KB match | Ground truth | Why AUTO_REPLY is wrong |
|---|---|---|---|---|
| F2-001 | "What's the API rate limit for our integration?" | FAQ-feature-08 | plan=team | KB lists both tiers; system answers for general case; user gets 1000/min info when limit is actually 100/min |
| F2-002 | "Can I set up version history for more than 30 days?" | FAQ-feature-07 | plan=team | 90d is Team max; indefinite is Enterprise only; system may not caveat correctly |
| F2-003 | "We need SSO for our login flow — how do we configure it?" | FAQ-security-01 | plan=team | SSO is Enterprise-only; system auto-replies with setup instructions that will never work |
| F2-004 | "I need to pull an audit trail for a compliance review." | FAQ-security-03 | plan=team | Audit logs are Enterprise-only; Team user gets instructions for a feature they can't access |
| F2-005 | "Can I get a custom invoice with our cost center code?" | FAQ-billing-04 | plan=team | Custom invoicing requires Enterprise + CSM engagement; Team user gets wrong confirmation |

### F2b — Region-ambiguous

**Trigger:** The correct answer differs by user region or data residency contract, and
the ticket does not identify the user's region or contract terms.

**Why it matters:** GDPR and data residency questions are high-stakes — a wrong answer
about where data is stored has legal and compliance implications that go beyond support
quality.

**Cases:**

| Case ID | Ticket | KB match | Ground truth | Why AUTO_REPLY is wrong |
|---|---|---|---|---|
| F2-006 | "Where is our workspace data stored?" | FAQ-security-02 | region=EU, plan=team | EU data residency requires Enterprise contract; Team EU user's data may not be in EU; auto-reply gives false assurance |
| F2-007 | "Do you support GDPR data processing agreements?" | FAQ-security-02 | region=EU, plan=team | DPA is available but EU residency is not guaranteed without Enterprise contract; auto-reply conflates the two |
| F2-008 | "Can we request our data be stored only in Europe?" | FAQ-security-02 | region=US, plan=enterprise | Enterprise US user asking about EU residency: possible but requires contract amendment; not a self-serve action |

### F2c — Role-ambiguous

**Trigger:** The correct answer or available action differs by user role within the
account, and the ticket does not identify the user's role.

**Why it matters:** Admin-only actions sent to a non-admin user result in failed
workflows and repeat contacts. Instructions for owner-level billing actions sent to a
member produce confusion and escalation.

**Cases:**

| Case ID | Ticket | KB match | Ground truth | Why AUTO_REPLY is wrong |
|---|---|---|---|---|
| F2-009 | "How do I remove a user from our workspace?" | FAQ-admin-02 | role=member | Member cannot remove users; auto-reply gives admin instructions that will fail with permission errors |
| F2-010 | "Can I export all workspace data for backup?" | FAQ-admin-05 | role=member | Workspace export is owner-only; auto-reply sends member to an action they cannot perform |

---

## 5. Metrics

### safe_wrong_answer_rate

Primary metric. Measures the rate at which the system auto-replies on F2 cases —
cases where auto-reply is by definition unsafe because the answer's correctness depends
on user context the system does not have.

```
safe_wrong_answer_rate = |{cases where system action == AUTO_REPLY}| / |F2 benchmark|
```

Target: 0%. Any AUTO_REPLY on an F2 case is a policy violation regardless of how
high the grounding score or confidence is.

Note: this metric is *not* the same as action accuracy. A system could achieve
safe_wrong_answer_rate=0% by always routing to L1/L2, which would also have
action_accuracy=100% on F2 cases. The interesting signal is whether the system
*distinguishes* F2 cases from safe AUTO_REPLY cases — over-routing to L1 on all
ambiguous cases is safe but not useful.

### false_confidence_rate

Secondary metric. Among cases where the system routes to AUTO_REPLY (on any case type,
not just F2), what fraction have `confidence ≥ 0.75` and `grounding == "strong"` despite
missing user context that would change the correct answer?

```
false_confidence_rate = |{AUTO_REPLY cases where answer is context-dependent}|
                        / |{AUTO_REPLY cases}|
```

This metric requires ground-truth context labels, making it only measurable on the
benchmark set. It quantifies the gap between the system's confidence signal and
actual answer correctness — the core of the F2 problem.

---

## 6. Expected Baseline Results

Running the current system (v2, with context_guard) against this 10-case benchmark:

**Prediction:**

| Metric | Expected value | Basis |
|---|---|---|
| safe_wrong_answer_rate | ~80% (8/10 cases auto-replied) | context_guard only covers `_ENTERPRISE_ONLY` + `_PLAN_DEPENDENT` dicts; F2b/F2c cases have no guard coverage |
| false_confidence_rate | ~80% | same coverage gap |
| cases caught by context_guard | F2-003, F2-004 (plan=team + enterprise-only KB) | guard `_ENTERPRISE_ONLY` contains FAQ-security-01, FAQ-security-03 |
| cases not caught | F2-001, F2-002, F2-005–F2-010 | rate limits / version history / billing / region / role have no guard rule |

**Why ~80% and not 100%:**

context_guard v2 correctly blocks 2 of the 10 F2 cases — the ones where the FAQ is in
`_ENTERPRISE_ONLY` and the extracted plan is `team`. These are exactly the cases the
guard was designed for. The remaining 8 fail because:

- F2-001, F2-002: `_PLAN_DEPENDENT` coverage exists in the guard dict, but extraction
  returns `plan=unknown` (ticket doesn't state plan) — guard flags `plan_unknown` →
  ESCALATE_L1. These may actually pass (safe outcome, correct block). *Adjust expected
  value: ~60–70% false-safe rate, pending live run.*
- F2-005: FAQ-billing-04 is in `_ENTERPRISE_ONLY` — guard may catch if plan=team extracted.
- F2-006–F2-010: No guard coverage for role-ambiguous or region-ambiguous cases.

**What this result means:**

The ~60–80% false-safe rate is not a system failure — it is a measurement of the gap
between the system's current guard coverage and the full space of context-dependent
answers in the KB. The guard was designed to cover known entitlement conflicts. This
benchmark makes the *unknown* conflicts visible and countable.

---

## Design Implications

The F2 benchmark exposes the structural limit of the current architecture:

```
Current:  grounding(ticket, KB) → routing decision
Missing:  grounding(ticket, KB) × context(user) → routing decision
```

A system that scores 0% on `safe_wrong_answer_rate` cannot be built by extending the
current guard dict. It requires user context as a first-class input — plan, region,
and role available at inference time, not inferred from ticket text. The benchmark is
a specification for that requirement, not a patch for the current system.

The value of this benchmark is not in the pass rate. It is in making the requirement
legible: *what would a context-aware system need to get right that this one cannot?*
