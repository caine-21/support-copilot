# Support Copilot Production Verification — 2026-08

This note records the productionization boundary and the evidence collected
for the public Render prototype. Claims are labeled by verification level.

## Release Boundary

- [Production verified] URL: `https://support-copilot-qiun.onrender.com/`
- [Production verified before this patch] Render service: `support-copilot`, Docker Web Service, staging mode.
- [Production verified before this patch] Deployed `/version`: `0.6.0`, `git_sha=unknown`, `deployment_mode=staging`.
- [Not verified yet] This productionization patch's deploy commit and post-deploy smoke.

## Production Architecture

```text
HTTP request
→ request-id / trusted-host / body-size / auth / rate-limit boundary
→ FastAPI route + Pydantic validation
→ TicketWorkflowService
→ deterministic A1 retrieval / grounding / risk / authorization gate
→ AUTO_REPLY / ESCALATE_L1 / ESCALATE_L2
→ redacted response + JSON telemetry
```

The public web channel is provider-free and stateless-by-default. SQLite and
bounded traces are process-local; no PostgreSQL, Redis, Celery, or external
customer-system integration is required at the current synchronous prototype
boundary.

## Baseline Smoke Before Patch

- [Production verified] `/livez` → 200, `{"status":"alive"}`.
- [Production verified] `/readyz` → 200, database and knowledge base ready, provider calls disabled.
- [Production verified] `/health` → 200; retained as legacy compatibility, not the deploy gate.
- [Production verified] normal Chinese refund request → 201, `AUTO_REPLY`, `grounding_safe=true`.
- [Production verified] missing field, wrong type, and oversize public requests → 422, no 500.
- [Production verified] supplied `X-Request-ID` was returned in the response header.

## Local Gates

- [Tested locally] `py -m pytest tests/ops/test_productionization.py tests/ops/test_config_and_api.py tests/ops/test_provider_and_idempotency.py tests/ops/test_failure_matrix.py tests/ops/test_regression_candidate.py -q -p no:cacheprovider` → 28 passed.
- [To run before merge] full `py -m pytest tests -q -p no:cacheprovider`.
- [To run before merge] `py scripts/check_text_integrity.py --all-text`.

## Failure Exercise

- [Tested locally] injected failure: one `TimeoutError` from a decision double.
- [Tested locally] observed: workflow became `failed`, decision `UNKNOWN`.
- [Tested locally] classification: `provider_timeout` in structured telemetry.
- [Tested locally] recovery: next provider-free grounded request completed as `AUTO_REPLY` with `grounding_safe=true`.
- [Tested locally] secret leakage: false; no provider key or injected exception text in logs.
- [Not verified] intentional provider failure against Render; deliberately not performed.

## Observability

- [Implemented and tested locally] request ID reuse/generation and response header propagation.
- [Implemented and tested locally] JSON `request_completed` fields: method, path, status code, route, request ID, latency.
- [Implemented and tested locally] bounded in-process metrics and trace storage.
- [Implemented and tested locally] redaction of ticket text, authorization, token, email, password, and draft fields.
- [Production verified before this patch] Render `/version` exposed `git_sha=unknown`; this patch falls back to Render's `RENDER_GIT_COMMIT` when the build arg is unknown.

## Security and Boundaries

- [Checked] `.env` is ignored and was not read or committed during this work.
- [Implemented] public validation max length is 2,000 characters; request body and concurrency limits are configured.
- [Implemented] single-process best-effort rate limiting; this is not a distributed limiter.
- [Implemented] provider calls and executor actions remain disabled on the public web path.
- [Known limitation] logs, metrics, SQLite, and traces are process-local on Render Free; no durable audit or cross-instance guarantee.

## Verdict Before Deployment

`PARTIAL` until this patch is merged, deployed, and the post-deploy smoke plus
version identity are recorded. Do not call this enterprise-grade,
high-availability, or a real customer-service integration.
