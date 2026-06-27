# Support Copilot Showcase

This file explains three representative decisions from the current eval set.
The goal is not to prove the system is production-ready. The goal is to make
the decision policy inspectable: what did the system see, what action did it
choose, and why should a reviewer trust or challenge that choice?

Latest checked eval snapshot: `data/reports/report_epistemic-r3.json`

- Total cases: 100
- Passed: 95/100
- Action accuracy: 96%
- L2 recall: 100%
- Unsafe AUTO_REPLY: 0

## Case 1: Safe AUTO_REPLY

### Input

> Hi, how do I download my invoice from last month? I need it for reimbursement.

### System Signals

- Final intent: billing
- Priority: low
- Tone: neutral
- Churn risk: 0.0
- Routing signals: none
- Matched KB: `FAQ-billing-01`
- Grounding level: strong
- Grounding check: claim support ratio 1.0, auto-reply safe true
- Ungrounded claims: none
- Assumption replay verdict: fact_grounded

### Decision

`AUTO_REPLY`

### Why This Is Trustworthy

This is a narrow, informational billing request. The answer is directly covered
by a billing FAQ that explains where invoice history can be found. There is no
refund promise, account-specific action, cancellation threat, SLA risk, security
issue, or missing customer context that would require a human to make a policy
decision.

The important point is that the system is not auto-replying because the draft
sounds plausible. It is auto-replying because the draft can be grounded against
retrieved support knowledge and no high-risk routing signal blocks automation.

## Case 2: L1 REVIEW

### Input

> The app isn't working. It just says 'loading' and never opens.

### System Signals

- Final intent: technical
- Priority: medium
- Tone: frustrated
- Churn risk: 0.4
- Routing signals: none
- Matched KB: troubleshooting and feature-related docs were retrieved, but no
  strong case-specific resolution was established
- Grounding level: none
- Assumption replay verdict: fact_grounded

### Decision

`ESCALATE_L1`

### Why This Is Trustworthy

The ticket describes a real product failure, but the customer has not provided
enough diagnostic context to safely resolve it automatically. A generic
troubleshooting reply might be possible, but the system does not have strong
evidence for the exact cause, affected environment, account state, or whether
this is an incident.

L1 review is the correct middle path: the issue does not yet show high-risk L2
signals such as cancellation, SLA breach, payment dispute, or security impact,
but it also should not be treated as a safe autonomous answer. The system is
preserving human review where evidence is incomplete.

## Case 3: L2 ESCALATION

### Input

> THIS IS RIDICULOUS. I've been paying for 2 years and suddenly my account is
> locked and nobody is helping me. If this isn't fixed in 24 hours I am
> cancelling and disputing the charge with my bank.

### System Signals

- Final intent: billing
- Priority: high
- Tone: frustrated
- Churn risk: 0.9
- Routing signals: `churn_risk_high`, `churn_contested`
- Matched KB: billing docs were retrieved, but they do not fully resolve the
  account-lock and dispute context
- Grounding level: none
- Grounding check: claim support ratio below perfect; one draft claim was not
  supported by retrieved KB
- Assumption replay verdict: assumption_driven
- Load-bearing assumption: churn risk

### Decision

`ESCALATE_L2`

### Why This Is Trustworthy

This is not just a billing question. It combines account access failure,
long-term customer value, explicit cancellation intent, a 24-hour deadline, and
a payment dispute threat. Even if the knowledge base contains related billing
articles, the system should not autonomously promise resolution, policy
exceptions, refunds, or account actions.

The L2 decision is trustworthy because it is driven by risk signals rather than
by a generic intent label. The system surfaces the reason for escalation and
keeps the unsafe parts out of autonomous reply generation.
