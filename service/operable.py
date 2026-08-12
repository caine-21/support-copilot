"""Additive A6 staging composition root.

The A1-A5 ``service.api`` remains compatibility-stable. This module reuses its
ticket routes and installs the operational boundary used by Docker/staging.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import create_app as create_legacy_app
from .config import DeploymentMode, RuntimeSettings
from .customer_experience import customer_reply, demo_customer_context, is_human_handoff_request
from .domain import CustomerTicketRequest, CustomerTicketResponse, TicketCreate
from .engine import TicketWorkflowService
from .observability import Telemetry, bind_context, new_request_context
from .public_ui import PUBLIC_LANDING_PAGE as PUBLIC_PORTAL_PAGE
from .repository import InvalidTransition
from .runtime import readiness, runtime_decision_fn, version_payload


class InMemoryRateLimiter:
    """Single-process demo protection only; not distributed rate limiting."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            events = self._events[key]
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def _bearer(header: str | None, expected: str | None) -> bool:
    if not header or not expected or not header.startswith("Bearer "):
        return False
    return secrets.compare_digest(header[7:], expected)


def _route_label(path: str) -> str:
    """Bound metric/log cardinality and keep ticket/trace IDs out of routes."""
    if path.startswith("/tickets/"):
        suffix = path[len("/tickets/"):].split("/", 1)
        return "/tickets/{ticket_id}" + (f"/{suffix[1]}" if len(suffix) == 2 else "")
    if path.startswith("/ops/traces/"):
        return "/ops/traces/{trace_id}"
    return path


def _customer_reason(decision: str | None, ticket_text: str = "") -> str:
    """Translate internal routing details into a stable customer-facing explanation."""
    if is_human_handoff_request(ticket_text):
        return "已记录人工处理请求；当前公开演示通道暂未连接真人收件箱。"
    return {
        "AUTO_REPLY": "已找到可用的帮助中心依据，可以先参考这条回复。",
        "ESCALATE_L1": "当前依据不足以直接回答，建议人工客服进一步确认。",
        "ESCALATE_L2": "这个问题可能涉及账户或高风险操作，建议人工优先处理。",
        "UNKNOWN": "系统暂时无法完成判断，建议人工客服处理。",
    }.get(decision, "系统没有足够依据直接回答，建议人工客服处理。")


def create_operable_app(
    *,
    settings: RuntimeSettings | None = None,
    service: TicketWorkflowService | None = None,
    telemetry: Telemetry | None = None,
) -> FastAPI:
    cfg = settings or RuntimeSettings.from_env()
    ops = telemetry or Telemetry(cfg)
    svc = service or TicketWorkflowService(
        decision_fn=runtime_decision_fn(cfg),
        telemetry=ops,
    )
    if service is not None and getattr(service, "telemetry", None) is None:
        service.telemetry = ops
    app = create_legacy_app(service=svc)
    app.title = "support-copilot operable beta"
    app.version = cfg.app_version
    app.debug = False
    app.state.settings = cfg
    app.state.telemetry = ops
    app.state.ticket_service = svc

    if cfg.enable_provider_calls:
        from agent.llm import set_provider_observer

        def observe_provider(event: str, fields: dict) -> None:
            provider = str(fields.get("provider") or "unknown")
            if event in {"llm_call_succeeded", "llm_call_failed"}:
                status_label = "success" if event.endswith("succeeded") else str(fields.get("error_type") or "error")
                ops.metrics.inc("support_provider_request_count_total", {"provider": provider, "status": status_label})
                latency = fields.get("latency_ms")
                if isinstance(latency, (int, float)):
                    ops.metrics.observe("support_provider_latency_ms", float(latency), {"provider": provider})
                if fields.get("error_type") == "timeout":
                    ops.metrics.inc("support_provider_timeout_count_total", {"provider": provider})
                if fields.get("error_type") == "rate_limit":
                    ops.metrics.inc("support_provider_rate_limit_count_total", {"provider": provider})
            elif event == "provider_fallback":
                ops.metrics.inc("support_provider_fallback_count_total", {"provider": provider})
            ops.event(event, **fields)

        set_provider_observer(observe_provider)

    from agent.tooling import set_tool_observer

    def observe_tool(event: str, fields: dict) -> None:
        if event == "tool_call_completed":
            ops.metrics.inc(
                "support_tool_call_count_total",
                {"tool": str(fields.get("tool") or "unknown"), "status": str(fields.get("status") or "unknown")},
            )
        ops.event(event, tool_calls=1, **fields)

    set_tool_observer(observe_tool)

    if not cfg.enable_docs:
        hidden = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
        app.router.routes = [route for route in app.router.routes if getattr(route, "path", None) not in hidden]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(cfg.allowed_hosts))

    limiter = InMemoryRateLimiter(cfg.rate_limit_per_minute)
    concurrency = asyncio.Semaphore(cfg.max_concurrency)

    def authorize(path: str, method: str, authorization: str | None) -> JSONResponse | None:
        if path.startswith("/ops/") or path == "/metrics":
            if not cfg.enable_admin:
                return JSONResponse(status_code=404, content={"detail": "not found"})
            if not cfg.admin_token:
                return JSONResponse(status_code=503, content={"detail": "admin authentication not configured"})
            if not _bearer(authorization, cfg.admin_token):
                return JSONResponse(status_code=401, content={"detail": "authentication required"})
            return None
        if not path.startswith("/tickets") or cfg.deployment_mode is DeploymentMode.LOCAL:
            return None
        if cfg.public_ticket_allowed() and path == "/tickets" and method == "POST":
            return None
        if not cfg.api_token:
            return JSONResponse(status_code=503, content={"detail": "api authentication not configured"})
        if not _bearer(authorization, cfg.api_token):
            return JSONResponse(status_code=401, content={"detail": "authentication required"})
        if cfg.deployment_mode is DeploymentMode.DEMO and path.endswith("/review"):
            return JSONResponse(status_code=403, content={"detail": "review endpoint disabled in demo mode"})
        return None

    @app.middleware("http")
    async def operational_boundary(request: Request, call_next):
        context = new_request_context(
            request.headers.get("x-request-id"),
            request.headers.get("traceparent"),
        )
        bind_context(context)
        started = time.monotonic()
        path = request.url.path
        route_label = _route_label(path)

        blocked = authorize(path, request.method, request.headers.get("authorization"))
        if blocked is not None:
            response = blocked
        else:
            content_length = request.headers.get("content-length")
            too_large = False
            if content_length:
                try:
                    too_large = int(content_length) > cfg.max_request_bytes
                except ValueError:
                    too_large = True
            if too_large:
                ops.metrics.inc("support_request_error_count_total", {"error_type": "request_too_large"})
                response = JSONResponse(status_code=413, content={"detail": "request body too large"})
            elif path in {"/tickets", "/customer/tickets"} and request.method == "POST" and cfg.deployment_mode is not DeploymentMode.LOCAL and not await limiter.allow(request.client.host if request.client else "unknown"):
                ops.metrics.inc("support_request_error_count_total", {"error_type": "rate_limit"})
                response = JSONResponse(status_code=429, content={"detail": "demo rate limit exceeded"})
            else:
                acquired = False
                try:
                    try:
                        await asyncio.wait_for(concurrency.acquire(), timeout=0.25)
                        acquired = True
                    except TimeoutError:
                        ops.metrics.inc("support_request_error_count_total", {"error_type": "concurrency_limit"})
                        response = JSONResponse(status_code=503, content={"detail": "service concurrency limit reached"})
                    else:
                        ops.event("http_request_received", route=route_label)
                        try:
                            response = await asyncio.wait_for(call_next(request), timeout=cfg.request_timeout_seconds)
                        except TimeoutError:
                            ops.metrics.inc("support_request_error_count_total", {"error_type": "request_timeout"})
                            response = JSONResponse(status_code=504, content={"detail": "request deadline exceeded"})
                finally:
                    if acquired:
                        concurrency.release()

        latency_ms = round((time.monotonic() - started) * 1000, 2)
        response.headers["X-Request-ID"] = context.request_id
        response.headers["traceparent"] = context.traceparent
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        outcome = "success" if response.status_code < 500 else "error"
        ops.metrics.inc("support_request_count_total", {"route": route_label, "status": outcome})
        ops.metrics.observe("support_request_latency_ms", latency_ms, {"route": route_label})
        ops.event("request_completed", route=route_label, latency_ms=latency_ms, execution_state=str(response.status_code))
        return response

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/", response_class=HTMLResponse)
    def landing_page() -> HTMLResponse:
        return HTMLResponse(content=PUBLIC_PORTAL_PAGE)

    @app.post("/customer/tickets", response_model=CustomerTicketResponse, status_code=201)
    def create_customer_ticket(payload: CustomerTicketRequest) -> CustomerTicketResponse:
        if not cfg.customer_portal_allowed:
            raise HTTPException(status_code=404, detail="customer portal disabled")
        try:
            record = svc.create_ticket(
                TicketCreate(
                    ticket_text=payload.ticket_text,
                    user_id="anonymous-web",
                    customer_context=demo_customer_context(payload.profile.model_dump() if payload.profile else None),
                )
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        decision = record.decision
        next_step = {
            "AUTO_REPLY": "customer_can_continue",
            "ESCALATE_L1": "human_review_recommended",
            "ESCALATE_L2": "priority_human_review_recommended",
        }.get(decision, "human_review_recommended")
        return CustomerTicketResponse(
            ticket_id=record.ticket_id,
            status=record.workflow_status.value,
            decision=decision,
            reply=customer_reply(payload.ticket_text, decision, record.draft_response, record.retrieved_evidence),
            grounding_safe=record.grounding_safe,
            reason=_customer_reason(decision, payload.ticket_text),
            next_step=next_step,
        )

    @app.get("/readyz")
    def readyz():
        payload, ready = readiness(svc, cfg)
        return JSONResponse(status_code=200 if ready else 503, content=payload)

    @app.get("/version")
    def version() -> dict[str, str]:
        return version_payload(cfg)

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        return ops.metrics.render()

    @app.get("/ops/traces/{trace_id}")
    def get_trace(trace_id: str):
        normalized = trace_id.lower()
        if len(normalized) != 32 or any(char not in "0123456789abcdef" for char in normalized):
            raise HTTPException(status_code=422, detail="invalid trace id")
        events = ops.traces.get(normalized)
        if events is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return {"trace_id": normalized, "events": events}

    return app


app = create_operable_app()
