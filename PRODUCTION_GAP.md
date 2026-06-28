# Production Gap and POC Roadmap

## 1. Current Position

Support Copilot is a production-shaped portfolio / POC system. It is not a full
production support platform.

The current project already covers several parts of a real AI support automation
workflow:

- ticket routing
- grounding
- eval / regression
- run ledger
- assumption trace
- Gradio demo / showcase

The important distinction: this is not a generic chatbot demo. It is an
evidence-based routing system that asks whether a ticket has enough verified
support evidence for `AUTO_REPLY`, or whether it should move to `ESCALATE_L1` /
`ESCALATE_L2` with a clear handoff reason.

## 2. Production Gap Table

| Production system needs | Current gap | Portfolio / POC proof | Do now? |
|---|---|---|---|
| Real support platform integration: Zendesk / Intercom / Freshdesk adapter | Tickets are loaded from CLI, Gradio, and eval fixtures instead of a real queue. | Add a mock ticket adapter that accepts Zendesk-like ticket JSON and produces the same routing packet. | Yes, as a mock adapter. Do not use real credentials yet. |
| Structured customer context: plan / region / role / contract / SLA tier / account status | Context is mostly inferred from ticket text or hard-coded guard logic. | Add customer context fixtures and require routing to inspect structured context before `AUTO_REPLY`. | Yes, high priority. |
| Knowledge governance: KB health / gap recommendation / version / approval / expiry | KB entries are usable for retrieval, but do not yet carry governance metadata. | Annotate KB docs with constraints such as `min_plan`, `regions`, `risk_level`, `requires_human`, `source`, and `last_verified`. | Yes, high priority. |
| Online feedback loop: live traces -> human feedback -> dataset -> regression -> rollout | Eval data is offline and manually maintained. Human reviewer corrections do not yet become regression cases. | Simulate reviewer overrides and convert them into candidate eval fixtures. | Later in P1. Start with reviewer handoff packet first. |
| Standard observability: OpenTelemetry / LangSmith-style traces / latency / cost | The project has run ledger and assumption trace, but not standard tracing, latency, token cost, or provider-level spans. | Keep the run ledger as a portfolio-friendly trace; later add latency/cost fields without standing up a full tracing stack. | Not now. Add lightweight fields only when needed. |
| Multi-channel / multi-turn: chat / email / voice / social / handoff continuity | Current demo is single-ticket oriented and does not model channel-specific handoff continuity. | Use the same routing packet across mock email/chat tickets before adding multi-turn memory. | Not now. |
| Permission / compliance: SSO / RBAC / audit / PII redaction / data residency | No enterprise auth, no RBAC, no PII handling layer, no residency controls. | Document non-goals and use synthetic data only. Add PII redaction mock only if needed for a specific JD/demo. | Not now. |
| Production reliability: SLA / fallback / rate limit / queue / retry / incident monitoring | Provider fallback exists, but there is no real queue, rate-limit handling, retry policy, incident monitor, or service SLO. | For POC, show safe fallback behavior and batch readiness reporting; defer production operations. | Not now, except simple fallback evidence. |

## 3. Recommended Roadmap

### P0

- Keep commit boundaries clean.
- Keep the runnable portfolio baseline.
- Separate benchmark labels from runtime policy.
- Avoid mixing retrieval / routing / UI in one commit.

### P1

- Add `customer_context` schema + fixtures.
- Add KB annotation.
- Add Automation Readiness Report.
- Add mock ticket adapter.
- Add reviewer handoff packet.

### P2

- Real Zendesk / Intercom integration.
- Enterprise auth / RBAC.
- Standard tracing stack.
- Multi-channel conversation memory.
- Production deployment / monitoring.

## 4. Explicit Non-Goals

Do not build these now:

- real customer PII
- real Zendesk credentials
- enterprise SSO / RBAC
- full OpenTelemetry stack
- multi-region deployment
- complex frontend
- production incident management

These are real production concerns, but they are not the shortest path to making
this project stronger as a portfolio / POC system.

## 5. Next Best Implementation Slice

The next implementation slice should be:

- structured customer context fixture
- KB annotation
- Automation Readiness Report
- mock ticket adapter

Why this slice:

- These four items best prove SaaS/FDE implementation ability.
- They move the project from an offline agent demo toward a customer POC workflow.
- They do not require real customer data.
- They do not require real support platform credentials.
- They create clearer interview evidence than adding more prompt rules.
