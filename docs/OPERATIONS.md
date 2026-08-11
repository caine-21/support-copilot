# A6 Operations Guide

## Service contract

The deployable entrypoint is `service.operable:app`. `service.api:app` is the A1-A5 compatibility surface and is not a public deployment target.

| Mode | Ticket access | Provider default | Executor | Docs/admin |
|---|---|---:|---:|---:|
| `local` | open loopback development | on | on | docs on, admin off |
| `demo` | only `POST /tickets` when explicitly enabled | off | off | off |
| `staging` | bearer token required | off (explicit opt-in) | off | off |

Public/demo and the checked-in staging Blueprint are no-send systems. They use the deterministic decision path and `MockTicketActionAdapter`; there is no Zendesk, email, or CRM integration.

## Health and release identity

- `GET /livez`: process is serving requests. Never checks external providers.
- `GET /readyz`: SQLite schema, KB readability/version, and staging API auth are ready. Returns 503 on a core mismatch.
- `GET /version`: app, git SHA, build time, mode, schema, prompt, policy, and KB version.
- `GET /health`: legacy compatibility only; do not use it as a deployment gate.
- `GET /metrics` and `GET /ops/traces/{trace_id}`: hidden unless `ENABLE_ADMIN=true`, then require `SUPPORT_ADMIN_TOKEN`.

## Required staging configuration

```text
SUPPORT_DEPLOYMENT_MODE=staging
SUPPORT_API_TOKEN=<secret>
ENABLE_PROVIDER_CALLS=false
ENABLE_EXECUTOR=false
ENABLE_PUBLIC_DEMO=false
ENABLE_CUSTOMER_PORTAL=false
ENABLE_ADMIN=false
ENABLE_DOCS=false
```

The optional customer portal is a same-origin web channel at `/`. Set
`ENABLE_CUSTOMER_PORTAL=true` only when provider calls and executor actions are
both disabled. The browser calls `/customer/tickets`, which accepts only the
customer's text and returns a redacted decision/reply contract; it must never
receive `SUPPORT_API_TOKEN`. This is a beta channel, not a durable production
conversation system.

Optional release controls:

- `SUPPORT_EXPECTED_KB_VERSION`: makes KB drift fail readiness.
- `SUPPORT_GIT_SHA`, `SUPPORT_BUILD_TIME`: set by the image build/release system.
- `SUPPORT_ALLOWED_HOSTS`: comma-separated TrustedHost allowlist.
- `SUPPORT_MAX_REQUEST_BYTES`, `SUPPORT_MAX_CONCURRENCY`, `SUPPORT_RATE_LIMIT_PER_MINUTE`, `SUPPORT_REQUEST_TIMEOUT_SECONDS`.

Secrets must be injected by the platform. Never bake `.env` into the image; `.dockerignore` excludes it.

## Local staging-equivalent run

```powershell
$env:SUPPORT_DEPLOYMENT_MODE='staging'
$env:SUPPORT_API_TOKEN='<local-test-token>'
$env:ENABLE_PROVIDER_CALLS='false'
$env:ENABLE_EXECUTOR='false'
py -B -m uvicorn service.operable:app --host 127.0.0.1 --port 8765 --no-access-log
```

In a second terminal:

```powershell
$env:SUPPORT_API_TOKEN='<local-test-token>'
py -B scripts\smoke_staging.py --base-url http://127.0.0.1:8765
```

## Docker and Render

```powershell
docker build --build-arg SUPPORT_GIT_SHA=<sha> --build-arg SUPPORT_BUILD_TIME=<utc> -t support-copilot:a6 .
docker run --rm -p 7860:7860 support-copilot:a6
```

`render.yaml` is deployment-ready but does not create a service by itself. Manual authenticated steps:

1. Connect this GitHub repository in Render and apply the Blueprint.
2. Set `SUPPORT_API_TOKEN`; optionally set provider keys only after explicitly enabling provider calls.
3. Configure GitHub environment `staging` with `RENDER_DEPLOY_HOOK_URL`, `SUPPORT_API_TOKEN`, and `STAGING_BASE_URL`.
4. Run the `deploy-staging` workflow and retain its smoke artifact.

The free Render service has ephemeral local storage. SQLite is therefore staging/demo state, not durable production state. Keep one instance; do not claim cross-instance exactly-once semantics.

## Provider and cost boundary

Provider mode makes at most one DeepSeek call and, after failure, one Groq call. Timeout, rate limit, server error, invalid output, and fallback are structured events and metrics. There is no same-provider backoff retry in A6. The deterministic demo path uses a dedicated provider-free KB gateway.

## Verification commands

```powershell
py -B -m pytest tests -q -p no:cacheprovider
py -B -m ops.challenge --output ops\evidence\failure_matrix.json
py -B scripts\smoke_staging.py --base-url <url> --output artifacts\ops\staging_smoke.json
```

Load thresholds for the checked in harness are error rate below 1%, p95 below 2 seconds, and zero unsafe `AUTO_REPLY`. `ops/load/k6.js` is for a real staging URL; the committed local evidence uses a 32-request in-process burst.
