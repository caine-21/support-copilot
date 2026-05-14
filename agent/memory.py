"""
Agent memory: ticket history per user + KB search cache.
In-memory only (no persistence) — sufficient for demo and eval runs.
"""


class AgentMemory:
    def __init__(self):
        self._ticket_history: dict[str, list[dict]] = {}  # user_id → list of past tickets
        self._kb_cache: dict[str, list[dict]] = {}         # query → kb results

    # ── ticket history ────────────────────────────────────────────────────────

    def add_ticket(self, user_id: str, ticket: dict):
        self._ticket_history.setdefault(user_id, []).append(ticket)

    def get_history(self, user_id: str) -> list[dict]:
        return self._ticket_history.get(user_id, [])

    def has_recent_similar(self, user_id: str, intent: str) -> bool:
        """True if user opened a ticket with the same intent recently (dedup signal)."""
        history = self.get_history(user_id)
        for past in history[-5:]:
            if past.get("intent") == intent:
                return True
        return False

    # ── KB cache ──────────────────────────────────────────────────────────────

    def cache_kb(self, query: str, results: list[dict]):
        self._kb_cache[query] = results

    def get_cached_kb(self, query: str) -> list[dict] | None:
        return self._kb_cache.get(query)
