import sys
import os
import json
import re
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

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
        for name, client_fn, fallback_model in providers:
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
                return resp.choices[0].message.content
            except Exception as e:
                print(f"[LLM] {name} failed: {e}")
                last_err = e
                continue
        raise RuntimeError(f"All LLM providers failed. Last error: {last_err}")


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
