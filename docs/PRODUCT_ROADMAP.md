# Customer Support Product Roadmap

This document describes the product path for the customer-facing support
portal. It is intentionally separate from the deterministic routing core: a
new channel should adapt identity, transport, and user experience without
duplicating triage or safety policy.

## Product thesis

For a small Chinese business, the first useful product is not a large agent
platform. It is a lightweight entry point that can answer grounded questions,
explain when it cannot answer, and hand a case to a person without asking the
business to operate several disconnected consoles.

The current web portal is therefore a beta customer entry point:

- same-origin web UI at `/`;
- redacted ticket contract at `POST /customer/tickets`;
- provider and executor disabled by default;
- no browser access to `SUPPORT_API_TOKEN`;
- no claim of durable conversation history or real external-action execution.

The current implementation is suitable for demonstrating the interaction and
the fail-safe boundary. It is not yet a production omnichannel helpdesk.

## Channel architecture

All channels should converge on one canonical conversation contract:

```text
Web / PWA       WeChat Mini Program       iOS / Android       WeCom
     \                 |                      |                 /
      channel adapter: identity + inbound/outbound message mapping
                               |
                 tenant + conversation + auth layer
                               |
                    support-copilot routing core
                  grounding / policy / escalation decision
                               |
                 human queue and channel-specific delivery
```

An adapter may translate a WeChat `openid`, a web session, or an iOS account
into the same internal participant and conversation identifiers. The adapter
must not make its own model decision. This keeps routing, grounding, risk
gates, and evaluation behavior consistent across platforms.

## Recommended sequence

### P0 — Web beta (current)

Keep the current page deliberately small: common-question shortcuts, a clear
conversation surface, an explicit safety explanation, and a deterministic
customer-visible escalation state. Make it installable as a PWA only after
authentication, persistence, and privacy boundaries are defined.

### P1 — Real support workspace

Before adding more channels, add the foundations that make a ticket useful to
a small business:

1. Postgres (or another durable store) for tenants, users, conversations,
   messages, assignments, and audit events;
2. customer authentication and tenant isolation, with short-lived sessions
   and server-side authorization;
3. an operator inbox with assignment, internal notes, status transitions,
   escalation reason, and reply delivery;
4. webhook/event records and idempotency keys so channel retries do not create
   duplicate tickets;
5. PII redaction, retention/deletion controls, rate limits, tracing, and
   alerting.

An existing product such as Chatwoot is a useful reference for the inbox and
channel abstraction. It should be evaluated as an operator-inbox integration
or a deployment reference before considering a fork of its full frontend.

### P2 — WeChat-first distribution

For Chinese individual businesses, prioritize a WeChat Mini Program or a
WeCom entry point before a native iOS app:

- use a Mini Program page for structured self-service and conversation;
- use the platform customer-service entry point when a human needs to take
  over;
- exchange platform identity for a server-side participant mapping;
- keep provider credentials, tenant policy, and channel secrets on the
  backend;
- send inbound events through the same conversation gateway and deliver the
  approved reply through a signed, idempotent outbound adapter.

The Mini Program should be a thin channel client, not a second support brain.
This reduces duplicated policy and makes it possible to add an official
account, WeCom, or a website widget later without rewriting the core.

### P3 — Mobile app when there is a validated need

Do not start with a native iOS app. First validate repeat usage through the
web/PWA and WeChat. If operators need push notifications, offline drafts,
camera/file workflows, or a dedicated multi-tenant workspace, reuse the same
API with React Native/Expo or Capacitor. Native distribution then becomes a
delivery decision, not a rewrite of the support system.

App Store submission also requires a privacy policy, data-handling disclosure,
account and deletion behavior where applicable, and review access that does
not depend on private credentials. These should be treated as product
requirements from P1 onward.

## Explicit production gaps

The following are intentionally not hidden by the current UI:

- the Render beta must move from ephemeral SQLite to durable storage;
- there is no operator authentication, tenant model, or human reply queue;
- the current public endpoint is unauthenticated and should remain a bounded
  demo until abuse controls and retention policy are implemented;
- no real WeChat, WeCom, email, or iOS credentials are wired;
- provider calls and external actions remain disabled until their audit,
  approval, retry, and rollback behavior is implemented and evaluated.

This order makes the project more credible: first prove a safe customer
interaction, then prove durable operations, then add distribution channels.
