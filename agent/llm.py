import sys
import os
import json
import logging
import re
import time
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv


_logger = logging.getLogger("support_copilot.provider")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO)
_logger.propagate = False
_provider_observer = None


def set_provider_observer(observer) -> None:
    global _provider_observer
    _provider_observer = observer


def classify_provider_error(exc: Exception) -> tuple[str, int | None]:
    """Stable operational taxonomy without logging provider error text."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or "timeout" in name:
        return "timeout", status
    if status == 429 or "ratelimit" in name or "rate_limit" in name:
        return "rate_limit", status
    if isinstance(status, int) and status >= 500:
        return "server_error", status
    if "connection" in name:
        return "connection_failure", status
    if status in {401, 403} or isinstance(exc, (ValueError, KeyError)) or "authentication" in name:
        return "auth_or_config", status
    if isinstance(exc, (json.JSONDecodeError, TypeError)):
        return "invalid_response", status
    return "unknown", status


def _provider_event(event: str, **fields) -> None:
    _logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, separators=(",", ":")))
    if _provider_observer is not None:
        _provider_observer(event, fields)


def _load_provider_config() -> None:
    """Load provider configuration only at a real-provider boundary.

    Importing contracts, scripted adapters, or no-service test harnesses must
    never read `.env` as a side effect.
    """
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))


class LLMRouter:
    """
    Provider-independent LLM abstraction.
    Primary: DeepSeek (OpenAI-compatible API, cheapest per token).
    Fallback: Groq (free tier, llama-3.3-70b-versatile).
    Adding a new provider = add one method + one entry in _providers list.
    """

    def __init__(self):
        self._ds_client = None
        self._groq_client = None

    def _deepseek(self):
        if self._ds_client is None:
            _load_provider_config()
            from openai import OpenAI
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise ValueError("DEEPSEEK_API_KEY not set")
            self._ds_client = OpenAI(
                api_key=key,
                base_url="https://api.deepseek.com",
            )
        return self._ds_client

    def _groq(self):
        if self._groq_client is None:
            _load_provider_config()
            from openai import OpenAI
            key = os.environ.get("GROQ_API_KEY")
            if not key:
                raise ValueError("GROQ_API_KEY not set")
            self._groq_client = OpenAI(
                api_key=key,
                base_url="https://api.groq.com/openai/v1",
            )
        return self._groq_client

    # Per-provider timeouts (seconds). DeepSeek is primary — short timeout so Groq fallback
    # kicks in quickly when the API hangs (common during eval runs).
    _TIMEOUTS = {"deepseek": 30, "groq": 60}

    def call(
        self,
        messages: list[dict],
        model: str = "deepseek-chat",
        json_mode: bool = True,
        temperature: float = 0.3,
    ) -> str:
        """
        Route: DeepSeek → Groq fallback.
        messages: standard OpenAI format [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        providers = [
            ("deepseek", self._deepseek, "deepseek-chat"),
            ("groq",     self._groq,    "llama-3.3-70b-versatile"),
        ]
        last_err = None
        for provider_index, (name, client_fn, fallback_model) in enumerate(providers):
            if provider_index:
                _provider_event("provider_fallback", provider=name, fallback_used=True)
            started = time.monotonic()
            _provider_event("llm_call_started", provider=name, provider_attempt=1)
            try:
                client = client_fn()
                use_model = model if name == "deepseek" else fallback_model
                kwargs = dict(
                    model=use_model,
                    messages=messages,
                    max_tokens=800,
                    temperature=temperature,
                    timeout=self._TIMEOUTS[name],
                )
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content
                if not isinstance(content, str) or not content.strip():
                    raise TypeError("invalid provider response")
                _provider_event(
                    "llm_call_succeeded", provider=name, provider_attempt=1,
                    fallback_used=provider_index > 0,
                    latency_ms=round((time.monotonic() - started) * 1000, 2),
                )
                return content
            except Exception as e:
                error_type, status_code = classify_provider_error(e)
                _provider_event(
                    "llm_call_failed", provider=name, provider_attempt=1,
                    error_type=error_type, status_code=status_code,
                    retryable=False,
                    latency_ms=round((time.monotonic() - started) * 1000, 2),
                )
                last_err = e
                continue
        last_type, _ = classify_provider_error(last_err) if last_err else ("unknown", None)
        raise RuntimeError(f"All LLM providers failed. Last error type: {last_type}")

    def call_with_tools(self, messages: list[dict], tools: list[dict], model: str = "deepseek-chat"):
        """Native OpenAI-compatible function calling; no JSON-in-text emulation."""
        providers = [("deepseek", self._deepseek, "deepseek-chat"), ("groq", self._groq, "llama-3.3-70b-versatile")]
        last_err = None
        for provider_index, (name, client_fn, fallback_model) in enumerate(providers):
            if provider_index:
                _provider_event("provider_fallback", provider=name, fallback_used=True)
            started = time.monotonic()
            _provider_event("llm_call_started", provider=name, provider_attempt=1, tool_mode=True)
            try:
                response = client_fn().chat.completions.create(
                    model=model if name == "deepseek" else fallback_model,
                    messages=messages, tools=tools, tool_choice="auto", max_tokens=800,
                    temperature=0.2, timeout=self._TIMEOUTS[name],
                )
                if not getattr(response, "choices", None):
                    raise TypeError("invalid provider response")
                _provider_event(
                    "llm_call_succeeded", provider=name, provider_attempt=1,
                    fallback_used=provider_index > 0, tool_mode=True,
                    latency_ms=round((time.monotonic() - started) * 1000, 2),
                )
                return response
            except Exception as exc:
                error_type, status_code = classify_provider_error(exc)
                _provider_event(
                    "llm_call_failed", provider=name, provider_attempt=1,
                    error_type=error_type, status_code=status_code,
                    retryable=False, tool_mode=True,
                    latency_ms=round((time.monotonic() - started) * 1000, 2),
                )
                last_err = exc
        last_type, _ = classify_provider_error(last_err) if last_err else ("unknown", None)
        raise RuntimeError(f"All native tool providers failed. Last error type: {last_type}")


# module-level singleton — import and use directly
router = LLMRouter()


def call_llm(system: str, user: str, provider: str = "auto", json_mode: bool = True) -> str:
    """Thin wrapper for backward compatibility. Uses router internally."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    if provider == "groq":
        # force Groq by temporarily routing directly
        client = router._groq()
        kwargs = dict(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=800,
            temperature=0.3,
            timeout=60,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kwargs).choices[0].message.content
    return router.call(messages, json_mode=json_mode)


def safe_json_parse(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return {}
