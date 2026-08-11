"""Typed A6 runtime configuration with fail-safe public defaults."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class DeploymentMode(str, Enum):
    LOCAL = "local"
    DEMO = "demo"
    STAGING = "staging"


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _integer(env: Mapping[str, str], name: str, default: int, *, minimum: int) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _number(env: Mapping[str, str], name: str, default: float, *, minimum: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _metadata(value: str | None, default: str) -> str:
    candidate = (value or default).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:+-]{1,128}", candidate):
        return default
    return candidate


@dataclass(frozen=True)
class RuntimeSettings:
    deployment_mode: DeploymentMode
    app_version: str
    git_sha: str
    build_time: str
    schema_version: str
    policy_version: str
    prompt_version: str
    expected_kb_version: str | None
    enable_provider_calls: bool
    enable_tool_loop: bool
    enable_multi_agent_shadow: bool
    enable_public_demo: bool
    enable_customer_portal: bool
    enable_executor: bool
    enable_fault_injection: bool
    enable_admin: bool
    enable_docs: bool
    api_token: str | None
    admin_token: str | None
    max_request_bytes: int
    max_concurrency: int
    rate_limit_per_minute: int
    request_timeout_seconds: float
    allowed_hosts: tuple[str, ...]

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "RuntimeSettings":
        env = environ if environ is not None else os.environ
        raw_mode = env.get("SUPPORT_DEPLOYMENT_MODE", "local").strip().lower()
        try:
            mode = DeploymentMode(raw_mode)
        except ValueError as exc:
            raise ValueError("SUPPORT_DEPLOYMENT_MODE must be local, demo, or staging") from exc

        provider_default = mode is DeploymentMode.LOCAL
        executor_default = mode is DeploymentMode.LOCAL
        docs_default = mode is DeploymentMode.LOCAL
        host_default = (
            "localhost,127.0.0.1,testserver"
            if mode is DeploymentMode.LOCAL
            else "localhost,127.0.0.1,*.onrender.com,*.hf.space"
        )
        allowed_hosts = tuple(
            item.strip() for item in env.get("SUPPORT_ALLOWED_HOSTS", host_default).split(",")
            if item.strip()
        )
        if not allowed_hosts:
            raise ValueError("SUPPORT_ALLOWED_HOSTS must contain at least one host")

        return cls(
            deployment_mode=mode,
            app_version=_metadata(env.get("SUPPORT_APP_VERSION"), "0.6.0"),
            git_sha=_metadata(env.get("SUPPORT_GIT_SHA"), "unknown"),
            build_time=_metadata(env.get("SUPPORT_BUILD_TIME"), "unknown"),
            schema_version="2",
            policy_version=_metadata(env.get("SUPPORT_POLICY_VERSION"), "authorization-v4"),
            prompt_version=_metadata(env.get("SUPPORT_PROMPT_VERSION"), "kb-closure-v6"),
            expected_kb_version=env.get("SUPPORT_EXPECTED_KB_VERSION") or None,
            enable_provider_calls=_flag(env, "ENABLE_PROVIDER_CALLS", provider_default),
            enable_tool_loop=_flag(env, "ENABLE_TOOL_LOOP", False),
            enable_multi_agent_shadow=_flag(env, "ENABLE_MULTI_AGENT_SHADOW", False),
            enable_public_demo=_flag(env, "ENABLE_PUBLIC_DEMO", False),
            enable_customer_portal=_flag(env, "ENABLE_CUSTOMER_PORTAL", False),
            enable_executor=_flag(env, "ENABLE_EXECUTOR", executor_default),
            enable_fault_injection=_flag(env, "ENABLE_FAULT_INJECTION", False),
            enable_admin=_flag(env, "ENABLE_ADMIN", False),
            enable_docs=_flag(env, "ENABLE_DOCS", docs_default),
            api_token=env.get("SUPPORT_API_TOKEN") or None,
            admin_token=env.get("SUPPORT_ADMIN_TOKEN") or None,
            max_request_bytes=_integer(env, "SUPPORT_MAX_REQUEST_BYTES", 16_384, minimum=1_024),
            max_concurrency=_integer(env, "SUPPORT_MAX_CONCURRENCY", 8, minimum=1),
            rate_limit_per_minute=_integer(env, "SUPPORT_RATE_LIMIT_PER_MINUTE", 30, minimum=1),
            request_timeout_seconds=_number(env, "SUPPORT_REQUEST_TIMEOUT_SECONDS", 20.0, minimum=0.1),
            allowed_hosts=allowed_hosts,
        )

    @property
    def deployment_version(self) -> str:
        return f"{self.app_version}+{self.git_sha[:12]}"

    @property
    def protected_api_ready(self) -> bool:
        if self.deployment_mode is DeploymentMode.STAGING:
            return bool(self.api_token)
        return True

    def public_ticket_allowed(self) -> bool:
        return (
            self.deployment_mode is DeploymentMode.DEMO
            and self.enable_public_demo
            and not self.enable_provider_calls
        )

    @property
    def customer_portal_allowed(self) -> bool:
        """Allow the redacted public channel only when no external effects are enabled."""
        return self.enable_customer_portal and not self.enable_provider_calls and not self.enable_executor
