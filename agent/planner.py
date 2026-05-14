"""
Planner: creates the fixed tool execution plan for a support ticket.
Order: classify_intent → kb_search → history_lookup → draft_reply → tone_check
"""


def create_plan(ticket_text: str, user_id: str) -> list[dict]:
    print(f"[Planner] ticket={ticket_text[:60]}...")
    plan = [
        {
            "step": 1,
            "tool": "classify_intent",
            "input_key": "ticket_text",
            "reason": "determine intent category and confidence before any other step",
        },
        {
            "step": 2,
            "tool": "kb_search",
            "input_key": "query",
            "reason": "retrieve relevant FAQ snippets to ground the reply",
        },
        {
            "step": 3,
            "tool": "history_lookup",
            "input_key": "user_id",
            "reason": "check if user has prior open tickets on same issue (dedup signal)",
        },
        {
            "step": 4,
            "tool": "draft_reply",
            "input_key": "ticket_text",
            "reason": "generate grounded reply using KB snippets",
        },
        {
            "step": 5,
            "tool": "tone_check",
            "input_key": "ticket_text",
            "reason": "detect frustration or churn risk to inform escalation decision",
        },
    ]
    print(f"[Planner] plan={[s['tool'] for s in plan]}")
    return plan
