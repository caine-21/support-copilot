# Support Copilot Production Verification — 2026-08

This note records the productionization boundary and the evidence collected
for the public Render prototype. Claims are labeled by verification level.

## Release Boundary

- [Production verified] URL: `https://support-copilot-qiun.onrender.com/`
- [Production verified before this patch] Render service: `support-copilot`, Docker Web Service, staging mode.
- [Production verified before this patch] Deployed `/version`: `0.6.0`, `git_sha=unknown`, `deployment_mode=staging`.
- [Production verified] productionization release `38447c2a3e665fd197e524dd8ec905c7423ad763` is live on the public URL.
- [Production verified] post-deploy public smoke passed on 2026-08-12; the detailed matrix is recorded below.
- [Known automation gap] the final `deploy-staging` run triggered Render successfully but timed out during the ten-minute readiness wait and skipped workflow smoke; direct public HTTP verification passed after recovery.

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
- [Verified in CI] full `py -m pytest tests -q -p no:cacheprovider` -> `226 passed`.
- [Verified locally] `py scripts/check_text_integrity.py --all-text` -> pass for 11 changed files.

## Post-deploy Public Smoke

- [Production verified] `/livez`, `/readyz`, and `/version` returned `200`; `/version.git_sha` matched `38447c2a3e665fd197e524dd8ec905c7423ad763`.
- [Production verified] supplied `X-Request-ID` was echoed on health, version, error, and ticket responses.
- [Production verified] unknown route returned bounded JSON with `error`, `errorType=not_found`, `requestId`, and `detail`; no framework traceback was exposed.
- [Production verified] missing field, wrong type, and 2,001-character input returned bounded `422` validation contracts.
- [Production verified] Chinese refund FAQ returned `201`, `AUTO_REPLY`, and `grounding_safe=true`.
- [Production verified] reproduced Chinese prompt-injection paraphrase returned `ESCALATE_L2` with `grounding_safe=false`.
- [Production verified] human-request input returned `ESCALATE_L1` and honestly stated that no live human inbox is connected.
- [Tested locally, not intentionally exhausted in production] rate limiting returned `429` under the configured 12 requests/minute boundary; no burst was sent to the public free-tier service.

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

## Current Verification Boundary

`PASS` for the bounded public prototype productionization scope. Structured
request telemetry and error contracts are implemented, covered by local tests
and CI, and exercised through public HTTP behavior. Render dashboard log search
was not independently queried because no Render API credential is configured in
the repository workflow; do not claim durable, cross-instance observability.
Do not call this enterprise-grade, high-availability, or a real
customer-service integration.
