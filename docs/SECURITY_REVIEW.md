# A6 Security Review

Date: 2026-08-10. Scope: Python/FastAPI A6 service boundary, configuration, telemetry, Docker and CI. This is a secure-by-default beta review, not a penetration test or production certification.

## Executive summary

No open critical/high finding was identified in the implemented A6 entrypoint. Public defaults remove provider, executor, docs, and admin capability; staging requires a bearer token; request models reject extra fields; request size/concurrency/deadlines are bounded; logs redact sensitive fields; and atomic action claims prevent concurrent duplicate adapter invocation.

## Findings

### SEC-01 ? Medium ? Wrong FastAPI entrypoint bypasses A6 controls

- Location: `service/api.py`, deployment configuration
- Impact: an operator who runs `service.api:app` directly gets the legacy unauthenticated compatibility API without A6 middleware.
- Mitigation: Docker, Render, docs, and CI all name `service.operable:app`. The legacy module is explicitly labeled compatibility-only.
- Remaining action: remove or hard-fail the legacy global app only in a separately reviewed breaking release.

### SEC-02 ? Low ? Rate limits and traces are process-local

- Location: `service/operable.py`, `service/observability.py`
- Impact: multiple replicas would have independent limits/metrics/traces and could not enforce a global abuse budget.
- Mitigation: A6 is documented and configured as single-instance staging; body, concurrency and deadline limits still apply per process.
- Remaining action: managed gateway/rate limit and durable telemetry before horizontal scale.

### SEC-03 ? Low ? Bearer token is coarse-grained, not RBAC

- Location: `service/operable.py`
- Impact: the staging token grants all protected ticket reads/writes. It has no user identity, rotation API, or per-action role.
- Mitigation: executor is disabled in staging, the action adapter is mock, admin uses a separate token, and secrets are platform-injected.
- Remaining action: identity-aware gateway/RBAC before real customer data or a real action adapter.

### SEC-04 ? Informational ? SQLite is not a distributed exactly-once system

- Location: `service/repository.py`
- Impact: the UNIQUE key and `BEGIN IMMEDIATE` protect one SQLite database, but cannot prove exactly-once against a real remote ticket system or multiple ephemeral instances.
- Mitigation: `in_progress` is treated as unknown and requires reconciliation; staging is single-instance/no-send.

### SEC-05 ? Low ? Body limit depends on the trusted edge `Content-Length`

- Location: `service/operable.py`
- Impact: a direct client using streaming/chunked transfer could avoid the middleware's early size check.
- Mitigation: the Render edge is the supported public ingress, request models cap relevant text fields, concurrency/deadlines are bounded, and no upload endpoint exists.
- Remaining action: use an ASGI receive-wrapper or gateway-enforced byte limit before exposing a direct ingress or file uploads.

## Controls verified

- FastAPI debug disabled; docs/OpenAPI hidden in public modes.
- TrustedHost allowlist and common browser security headers.
- Strict Pydantic request models, bounded text/IDs, body size limit.
- Staging/admin bearer checks use constant-time comparison.
- No `.env` in image; no secret values in `/version`, readiness, logs, or evidence.
- Dedicated deterministic gateway prevents public LLM fallback.
- Prompt-injection patterns route human-only.
- Provider error logs expose taxonomy/status, not raw exception/provider payload.
- Approval binds exact content hash; executor accepts only ticket ID; duplicate action claim is atomic.

## Verification

See `tests/ops`, `ops/evidence/failure_matrix.json`, and `ops/evidence/local_staging_smoke.json`. External dependency vulnerability scanning and a deployed perimeter test were not performed.
