# support-copilot — auditable ticket workflow slice

A bounded production slice on top of the existing offline decision pipeline.
It turns `run_agent`'s decision output into a **run → query → review → idempotent
action** loop with persistence and an audit trail. No real customer-support
system is ever called — the only action adapter wired by default is a mock.

> What this is NOT: not a real Zendesk/Intercom integration, not a real email
> sender, not multi-tenant, not a frontend. It is the auditable spine that a
> real integration would plug into.

## Why this slice exists

The original system was a strong **offline decision engine** (6 deterministic
gates, append-only run ledger, 100-case frozen eval) but it had no API, no
persistence of a ticket's full lifecycle, no human-review loop and no action
execution layer. Interviewers rightly said "demo-level, no real users". This
slice closes that specific gap without rewriting the engine.

## Architecture

```text
POST /tickets                      ──┐
    ↓  validate + save raw ticket    │ create + run
    ↓  run existing run_agent        │
    ↓  save decision/evidence/draft  │
    ↓  review_status = pending_review┘
GET /tickets/{id}                  → query state / decision / evidence / review / actions
POST /tickets/{id}/review          → approve | edit | reject
    ├─ rejected   → no action, audit row (skipped)
    ├─ approved   → decision gate → MockTicketActionAdapter.create_reply|create_escalation
    └─ edited     → uses edited_draft, then same idempotent action
```

- **Persistence**: SQLite via stdlib `sqlite3` (zero external services).
  Default DB `data/service/tickets.db`; override with `SUPPORT_DB_PATH`.
- **Idempotency key**: `{ticket_id}:{workflow_version}:{action_type}`.
  A review that already executed an action returns the recorded row —
  re-execution is impossible (enforced by a UNIQUE key + executed-status check).
- **Evidence gate**: an `AUTO_REPLY` whose `grounding_safe` is not `True` is
  blocked from executing — missing evidence cannot bypass the gate.
- **Failure handling**: a decision-flow error records the ticket as `failed`
  (never faked as success); an adapter exception records an `failed` action row
  and does not mark the workflow successful.
- **Trace**: each ticket run is linked to the existing append-only `RunLedger`
  (`data/runs/<run_id>/`) via `run_id`.

## Run

```bash
py -m pip install -r service/requirements.txt     # fastapi, uvicorn, httpx
py -m uvicorn service.main:app --port 8000
```

The API and DB are offline. A real decision requires `DEEPSEEK_API_KEY` /
`GROQ_API_KEY` (the existing agent stack loads `.env`).

```bash
curl -X POST localhost:8000/tickets \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id":"T-1","ticket_text":"How do I download my invoice?"}'
curl localhost:8000/tickets/T-1
curl -X POST localhost:8000/tickets/T-1/review \
  -H 'Content-Type: application/json' -d '{"reviewer_action":"approved"}'
```

## Tests

```bash
py -B -m pytest tests/test_ticket_service.py tests/test_ticket_api.py tests/test_action_adapter.py -q
```

21 offline tests (fake decision port injected; no API key, no network):
create/duplicate/query, decision persisted, failed-flow not marked success,
approve executes once, repeat approve does not re-execute, reject no-op,
**unsafe AUTO_REPLY blocked by evidence gate**, adapter failure recorded,
escalation path, cannot review a failed workflow, plus HTTP status codes.

## Verified evidence (2026-08-07)

- Full suite green: **70 passed** (49 pre-existing + 21 new), offline.
- Real decision path wired (one live run, `data/runs/…/service-api`):
  `REAL-1` → `completed`, decision `AUTO_REPLY`, `grounding_safe=True`,
  review executed `create_reply` once, ledger `run_id` linked.
- Live HTTP smoke: POST → GET → review(executed) → repeat review
  (idempotent, "already reviewed — no re-execution").

## Still NOT production

- Mock action adapter only; no real send/escalation.
- No real ticket traffic / real customer data.
- No auth/RBAC, no multi-tenancy, no queueing (FastAPI is synchronous here).
- Offline eval numbers remain offline eval numbers (see `CANONICAL_FACTS.md`).
