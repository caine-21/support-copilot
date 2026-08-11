# A6 Operator Runbook

## First five minutes

1. Read `/version`; record `git_sha`, `deployment_mode`, policy, prompt, and KB versions.
2. Check `/livez`, then `/readyz`. A live-but-not-ready instance must receive no traffic.
3. Correlate by `X-Request-ID` or `traceparent`; never search logs by raw customer text.
4. Check `support_request_error_count_total`, provider fallback/error counts, execution failures, and `support_unsafe_auto_violation_count_total`.
5. If an unsafe AUTO counter is non-zero, disable provider calls and executor immediately, preserve evidence, and roll back.

## Symptom matrix

| Symptom | Likely cause | Safe action |
|---|---|---|
| `/livez` 200, `/readyz` 503 | DB, KB/version, or staging token | inspect dependency map; do not bypass readiness |
| Provider timeout/429 spike | upstream or quota | keep one-fallback ceiling; switch to deterministic mode if acceptable |
| Both providers fail | upstream/config | workflow must be `failed/UNKNOWN`; route to human, never fabricate success |
| MCP timeout/error | tool transport | verify fail-closed L1/L2; keep executor disabled |
| DB locked/unavailable | single-node SQLite contention/storage | stop writes, preserve DB, restore last good instance; do not add workers |
| Action remains `in_progress` | process died after claim | reconcile mock/external target before any manual retry |
| KB version mismatch | code/data release skew | deploy the matching artifact or roll back; never override expected version |
| Prompt injection event | hostile/untrusted ticket | L2 human-only; preserve sanitized regression candidate |

## Kill switches

Restart the service with:

```text
ENABLE_PROVIDER_CALLS=false
ENABLE_TOOL_LOOP=false
ENABLE_MULTI_AGENT_SHADOW=false
ENABLE_EXECUTOR=false
ENABLE_PUBLIC_DEMO=false
ENABLE_ADMIN=false
```

Flags are immutable process-start configuration. A restart is required and `/version` plus `/readyz` must be rechecked.

## Rollback

1. Select the last image/deploy whose SHA has a passing CI artifact and 17/17 failure matrix.
2. Disable deploy automation while the incident is active.
3. Roll back the Render deploy or redeploy the prior image/commit.
4. Require `/readyz` 200 and confirm `/version.git_sha` is the intended prior SHA.
5. Run `scripts/smoke_staging.py`; restore traffic only after all cases pass.
6. Capture the incident, the before/after versions, and a sanitized regression candidate.

Rollback must not replay `in_progress` actions. Reconcile first.

## Evidence capture

```powershell
py -B -m ops.challenge --output artifacts\ops\failure_matrix.json
py -B scripts\capture_regression_candidate.py <sanitized-incident.json>
```

Candidates stay `pending_human_review`; an operator must define the expected action and approve promotion into a regression fixture.

## Escalation policy

- Security/unsafe AUTO: stop traffic and provider/executor capability immediately.
- Possible duplicate external action: no retry; human reconciliation required.
- Provider-only degradation with safe human routing: continue deterministic service if error budget permits.
- Missing secret or inaccessible hosting account: stop deployment work and request the account owner; do not create substitutes.
