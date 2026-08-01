# Multi-Agent Support Shadow Layer

## 1. Scope and status

This is an **offline-evaluated Multi-Agent Shadow POC**. It supports `off` (the default formal baseline) and `shadow` (an advisory packet attached to the baseline result). It does not provide active routing, real Provider calls in the evaluator, Zendesk/CRM integration, real customer-service execution, or production deployment.

## 2. Architecture

```text
Support Manager
├── Billing Specialist
└── Technical Specialist
```

The Support Manager is an independent call boundary and decides which, if any, specialists are called. Billing and Technical are independent specialists and can run in parallel. They return the shared Pydantic `SpecialistResult` contract. The Merger is deterministic code and never calls an LLM.

## 3. Shadow placement

```text
Phase 1 → Early-L2 gate → Multi-Agent Shadow → Original Draft → Original Grounding
→ Original Reasoner → Original Reflection → Final Baseline Action → Bind Shadow Packet
```

Shadow never enters the formal Draft prompt, Reasoner, or Authorization path, and cannot change the formal action. On Early-L2, Manager and Specialist calls are `0/0/0`; the packet is `skipped / early_l2`.

## 4. Domain Ticket Slices

Specialists never receive complete `ticket_text`. The Manager supplies domain-relevant original-ticket excerpts, and code verifies every excerpt is a direct ticket substring. Fabricated or rewritten excerpts are rejected. Billing and Technical receive different slices; unselected specialists receive none.

## 5. Explicit KB Domain Metadata

KB documents are explicitly tagged `billing`, `technical`, `shared`, or `unknown`. Billing receives only `billing/shared`, Technical receives only `technical/shared`, and `unknown` is not forwarded by default. Explicit document-domain mapping takes precedence over keyword inference.

## 6. Safe Error Model

```text
manager_json_invalid
manager_schema_invalid
manager_call_failed
billing_schema_invalid
billing_call_failed
technical_schema_invalid
technical_call_failed
report_write_failed
fixture_schema_invalid
```

Packet, ledger-facing data, and Eval JSON/Markdown records contain safe error fields only: no raw exceptions, tokens, absolute paths, email addresses, or internal URLs. Component-specific codes retain the failure source.

## 7. Three-Layer Oracle

Each of the 20 fixtures directly stores `business_oracle`, `injected_behavior`, `expected_observation`, `oracle_source`, and `oracle_notes`; there is no runtime legacy Oracle derivation.

### Business Oracle

Defines ideal Specialist selection, expected baseline action, `auto_reply_allowed`, Early-L2 business expectation, Manager quality, and Unsafe AUTO_REPLY eligibility.

### Injected Behavior

Defines scripted Manager/Specialist outputs including valid output, invalid JSON, invalid schema, injected exceptions, conflict, and leakage.

### Expected Observation

Defines observed selection, packet status, fallback flags, error codes, conflict/leakage detection, call counts, and skip reason.

## 8. Scenario Pass vs Quality Metrics

Correct injection, detection, and isolation of intentional bad behavior is a Scenario Pass. A Manager selection that differs from the Business Oracle independently lowers Manager Accuracy or Coverage. Consequently, `Scenario = 20/20` can coexist with `Manager Accuracy = 0.90` and `Multi-intent Coverage = 0.80`; Scenario Pass is not a claim that all Manager selections are correct.

## 9. Zero-Denominator Semantics

Every rate is structured. With no applicable samples it is reported as:

```json
{"value": null, "numerator": 0, "denominator": 0, "applicable": false, "vacuous": true}
```

`denominator=0` and `value=null` mean no applicable sample was observed, not 100% quality. This matters particularly for single-case Eval output.

## 10. Unsafe AUTO_REPLY

Unsafe AUTO_REPLY means `action == AUTO_REPLY` and `business_oracle.auto_reply_allowed == false`. The Eval separately reports `off_unsafe_auto_reply_count`, `shadow_unsafe_auto_reply_count`, and `unsafe_auto_reply_delta`. Delta zero alone is insufficient: Off unsafe, Shadow unsafe, and delta must all equal zero.

## 11. Eval Commands

Default Eval writes only to the console:

```powershell
py -B -m agent.multi_agent_eval
```

Run one fixture with `py -B -m agent.multi_agent_eval --case <case_id>`. Optional reports use `py -B -m agent.multi_agent_eval --out <directory>` and create `multi_agent_eval_report.json` and `multi_agent_eval_report.md`. A write failure is `report_write_failed`, without exposing a raw path or `PermissionError`.

## 12. Current Offline Evidence

The Scripted/Fake Offline Harness currently reports:

```text
cases = 20; scenario passed / failed = 20 / 0
manager selection accuracy = 0.90; multi-intent coverage = 0.80
off / shadow AUTO_REPLY = 1 / 1; off / shadow unsafe AUTO_REPLY = 0 / 0; unsafe delta = 0
completed / partial / failed / skipped = 14 / 1 / 3 / 2
canonical baseline, action, grounding, and customer-context unchanged rates = 1.0
tests = 48 passed
```

These are scripted-harness metrics, not real-model accuracy measures.

## 13. Canonical Cases

AUTO_REPLY uses formal T-001 invoice-download semantics, `FAQ-billing-01` strong grounding, and safe customer context: expected/Off/Shadow are all `AUTO_REPLY`. Canonical L1 remains `ESCALATE_L1`. Canonical L2 remains `ESCALATE_L2` with `0/0/0` calls and `skipped / early_l2` packet.

## 14. Evidence Boundary

This prototype demonstrates Manager/Specialist orchestration, independent call boundaries, context isolation, deterministic merging, contract validation, safe errors, failure recovery, Shadow invariants, and data-driven offline evaluation. It does not demonstrate real LLM quality, superiority over baseline, production safety, real customer resolution, token/latency gains, real Provider stability, or Zendesk/CRM integration.
