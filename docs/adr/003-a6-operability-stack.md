# ADR-003: A6 operability stack and staging target

- Status: Accepted for A6 Operable Beta
- Date: 2026-08-10

## Context

The A1-A5 runtime was locally verified but had no deployment contract, health split, release identity, protected operations surface, or repeatable failure challenge. A6 must add those properties without promoting the experimental Manager/Multi-Agent paths or weakening the deterministic authorization owner.

## Decision

1. Keep `app.runtime.run_a1.run_a1` as the canonical authorization workflow. Add `service.operable:app` as an additive FastAPI composition root; do not rewrite `service.api`.
2. Use typed environment flags for `local`, `demo`, and `staging`. Public defaults disable provider calls, executor tools, docs, admin surfaces, and Multi-Agent paths.
3. Use structured JSON events, W3C-compatible `traceparent`, Prometheus text metrics, and a bounded in-memory trace ring. Do not add Phoenix, Langfuse, or an OpenTelemetry collector in A6.
4. Keep provider behavior at one DeepSeek attempt followed by at most one Groq attempt. Do not add automatic same-provider retries: duplicate egress and cost expansion are a worse beta default than an explicit failure.
5. Use a Docker image and Render Blueprint as the deployment-ready staging target. The Blueprint uses an explicit free plan, `/readyz`, and deploy-after-checks. Actual resource creation remains an external authenticated action.
6. Keep feature flags as validated process-start configuration. Do not add OpenFeature until flags need a remote provider, runtime mutation, ownership metadata, and audit history.

## Consequences

- A6 gains a small dependency footprint and reproducible offline challenges.
- Metrics and traces are single-process and reset on restart; this is sufficient for an Operable Beta, not a production observability claim.
- SQLite and the in-memory rate limiter keep staging single-instance. Horizontal scale, durable traces, distributed rate limits, and real exactly-once delivery remain future work.
- The legacy `service.api:app` remains compatibility-only and must not be used as the staging entrypoint.

## Promotion criteria

Adopt a managed telemetry/flag stack only when there is a real remote staging service, more than one instance, an operator/on-call consumer, and a retention/audit requirement. Until then, machine-readable evidence is the source of truth.
