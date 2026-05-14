"""
Support Copilot tool registry.

Five tools: classify_intent, kb_search, history_lookup, draft_reply, tone_check.
Each wraps a Tool class compatible with osint-agent's fallback pattern.
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from llm import call_llm, safe_json_parse
import kb as kb_module


# ── Tool base class (reused from osint-agent) ─────────────────────────────────

class Tool:
    def __init__(self, name, fn, input_schema, output_schema, reliability, fallback=None):
        self.name = name
        self.fn = fn
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.reliability = reliability
        self.fallback = fallback

    def execute(self, input_data: dict) -> dict:
        print(f"[Tool] {self.name}...")
        try:
            result = self.fn(**input_data)
            return {"success": True, "data": result, "tool": self.name}
        except Exception as e:
            print(f"[Tool] {self.name} failed: {e}")
            if self.fallback:
                print(f"[Tool] falling back to {self.fallback.name}")
                return self.fallback.execute(input_data)
            return {"success": False, "error": str(e), "tool": self.name, "data": {}}


# ── Implementations ───────────────────────────────────────────────────────────

_INTENT_SYSTEM = """\
You are a SaaS support ticket classifier. Classify the ticket into exactly one intent.

Valid intents:
  billing       — invoice, payment, refund, seats, subscription price
  bug           — something is broken, not working, error, data loss
  how-to        — asking how to use a feature
  feature-request — asking for new functionality that doesn't exist yet
  account       — login, access, password, account settings, SSO
  churn         — explicit threat to cancel, leave, or dispute
  other         — does not fit any above category

Output JSON only:
{
  "intent": "<one of the above>",
  "confidence": <0.0–1.0>,
  "secondary_intent": "<second intent if multi-intent ticket, else null>",
  "reasoning": "<one sentence>"
}"""


def _classify_intent(ticket_text: str) -> dict:
    raw = call_llm(_INTENT_SYSTEM, f"Ticket: {ticket_text}")
    result = safe_json_parse(raw)
    return {
        "intent": result.get("intent", "other"),
        "confidence": float(result.get("confidence", 0.5)),
        "secondary_intent": result.get("secondary_intent"),
        "reasoning": result.get("reasoning", ""),
    }


def _kb_search_llm(query: str, top_k: int = 3) -> list[dict]:
    return kb_module.search(query, top_k=top_k)


def _kb_search_keyword(query: str, top_k: int = 3) -> list[dict]:
    """BM25-only fallback — explicit entry point for testing."""
    from kb import _bm25_search
    return _bm25_search(query, top_k=top_k)


def _history_lookup(user_id: str, memory=None) -> dict:
    """Return ticket history for the user from agent memory."""
    if memory is None:
        return {"past_tickets": [], "ticket_count": 0}
    history = memory.get_history(user_id)
    return {
        "past_tickets": history[-5:],
        "ticket_count": len(history),
    }


_DRAFT_SYSTEM = """\
You are a professional SaaS customer support agent for Acme Collab.
Write a helpful, concise reply grounded in the provided KB excerpts.
Rules:
  - Only reference information present in KB excerpts
  - If KB does not cover the question fully, acknowledge the gap explicitly
  - If the issue seems unresolved, offer to escalate
  - Professional but friendly tone
  - Max 150 words

Output JSON only:
{
  "reply": "<draft reply text>",
  "kb_used": ["<doc_id1>", "<doc_id2>"],
  "grounded": true/false,
  "gaps": "<what KB does not cover, or empty string>"
}"""


def _draft_reply(ticket_text: str, kb_snippets: list) -> dict:
    kb_block = "\n\n".join(
        f"[{item['doc_id']}]: {item['snippet']}" for item in kb_snippets
    ) if kb_snippets else "No KB results found."
    user_msg = f"Ticket: {ticket_text}\n\nKB Excerpts:\n{kb_block}"
    raw = call_llm(_DRAFT_SYSTEM, user_msg)
    result = safe_json_parse(raw)
    return {
        "reply": result.get("reply", ""),
        "kb_used": result.get("kb_used", []),
        "grounded": bool(result.get("grounded", False)),
        "gaps": result.get("gaps", ""),
    }


_TONE_SYSTEM = """\
Analyze the customer support ticket for emotional tone and churn risk.

Output JSON only:
{
  "tone": "frustrated" | "neutral" | "happy",
  "churn_risk": <0.0–1.0>,
  "churn_signals": ["<signal1>", ...],
  "urgency": "low" | "medium" | "high"
}

churn_signals: explicit or implicit signals (threats to cancel, negative reviews, comparing to competitors, "waste of money", repeated failures, etc.)
churn_risk: 0.0 = no risk, 1.0 = explicit cancellation intent"""


def _tone_check(ticket_text: str) -> dict:
    raw = call_llm(_TONE_SYSTEM, f"Ticket: {ticket_text}")
    result = safe_json_parse(raw)
    return {
        "tone": result.get("tone", "neutral"),
        "churn_risk": float(result.get("churn_risk", 0.0)),
        "churn_signals": result.get("churn_signals", []),
        "urgency": result.get("urgency", "medium"),
    }


# ── Fallback KB (keyword-only) ────────────────────────────────────────────────

_kb_fallback = Tool(
    name="kb_search_bm25",
    fn=_kb_search_keyword,
    input_schema={"query": "str", "top_k": "int"},
    output_schema={"results": "list[{doc_id, snippet, score}]"},
    reliability=0.65,
)

# ── Registry ──────────────────────────────────────────────────────────────────

tool_registry = {
    "classify_intent": Tool(
        name="classify_intent",
        fn=_classify_intent,
        input_schema={"ticket_text": "str"},
        output_schema={"intent": "str", "confidence": "float", "secondary_intent": "str|null"},
        reliability=0.90,
    ),
    "kb_search": Tool(
        name="kb_search",
        fn=_kb_search_llm,
        input_schema={"query": "str", "top_k": "int"},
        output_schema={"results": "list[{doc_id, snippet, score}]"},
        reliability=0.85,
        fallback=_kb_fallback,
    ),
    "history_lookup": Tool(
        name="history_lookup",
        fn=_history_lookup,
        input_schema={"user_id": "str", "memory": "AgentMemory|None"},
        output_schema={"past_tickets": "list", "ticket_count": "int"},
        reliability=0.99,
    ),
    "draft_reply": Tool(
        name="draft_reply",
        fn=_draft_reply,
        input_schema={"ticket_text": "str", "kb_snippets": "list"},
        output_schema={"reply": "str", "kb_used": "list", "grounded": "bool", "gaps": "str"},
        reliability=0.88,
    ),
    "tone_check": Tool(
        name="tone_check",
        fn=_tone_check,
        input_schema={"ticket_text": "str"},
        output_schema={"tone": "str", "churn_risk": "float", "churn_signals": "list"},
        reliability=0.85,
    ),
}
