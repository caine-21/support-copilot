"""
Agent loop: dispatch tool plan → reflection if confidence low → synthesize.
Adapted from osint-agent/agent_loop.py with support-copilot tool set.
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from planner import create_plan
from tools import tool_registry
from reasoner import synthesize
from memory import AgentMemory
from grounding_compiler import compile_grounding

DEBUG = True
MAX_ITER = 2


def log(tag: str, msg: str):
    if DEBUG:
        print(f"[{tag}] {msg}")


def decide_reflection_strategy(result: dict, iteration: int) -> dict | None:
    """
    Returns a strategy dict to retry with adjusted parameters, or None to stop.
    Mirrors osint-agent's approach: strategy-based, not blind rerun.
    """
    missing = " ".join(result.get("missing_info", []))
    action = result.get("action", "ESCALATE_L1")

    # Already L2 → no reflection will help; let it stand
    if action == "ESCALATE_L2":
        return None

    # No KB match → retry with broader query (strip stopwords, use intent label)
    if "no FAQ match" in missing or "no KB grounding" in missing:
        return {
            "tool": "kb_search",
            "reason": "no KB hit on first query — retry with intent-based broader query",
            "query_modifier": "how to help with",
        }

    # Intent ambiguous → reclassify with explicit hint
    if "intent ambiguous" in missing:
        return {
            "tool": "classify_intent",
            "reason": "intent was ambiguous — retry classification",
            "query_modifier": "",
        }

    return None


def run_tool_loop(
    ticket_text: str,
    ticket_id: str,
    user_id: str,
    plan: list[dict],
    memory: AgentMemory,
) -> dict:
    """Execute tool steps + grounding compiler; return observations dict."""
    obs = {
        "classification":  {},
        "kb_results":      [],
        "history":         {},
        "draft":           {},
        "tone":            {},
        "grounding_check": {},  # Milestone D: claim graph + KB support mapping
    }
    obs_keys = ["classification", "kb_results", "history", "draft", "tone"]

    for i, step in enumerate(plan):
        tool_name = step["tool"]
        log("Step", f"{step['step']}: {tool_name} — {step['reason']}")

        tool_obj = tool_registry[tool_name]

        # Build inputs per tool
        if tool_name == "classify_intent":
            inp = {"ticket_text": ticket_text}
        elif tool_name == "kb_search":
            # Pass raw ticket text — INL handles classification internally; intent prefix corrupts keyword rules
            query = ticket_text
            cached = memory.get_cached_kb(query)
            if cached is not None:
                log("Memory", f"KB cache hit for: {query[:50]}")
                obs["kb_results"] = cached
                continue
            inp = {"query": query, "top_k": 3}
        elif tool_name == "history_lookup":
            inp = {"user_id": user_id, "memory": memory}
        elif tool_name == "draft_reply":
            inp = {"ticket_text": ticket_text, "kb_snippets": obs["kb_results"]}
        elif tool_name == "tone_check":
            inp = {"ticket_text": ticket_text}
        else:
            log("Step", f"unknown tool {tool_name}, skipping")
            continue

        result = tool_obj.execute(inp)
        data = result.get("data", {}) if result["success"] else {}

        if tool_name == "kb_search" and result["success"]:
            memory.cache_kb(inp.get("query", ""), data)

        obs[obs_keys[i]] = data
        log("Obs", f"{tool_name} → {str(data)[:120]}")

        # After draft_reply: run grounding compiler to enforce KB closure (Milestone D)
        if tool_name == "draft_reply" and result["success"]:
            draft_text = data.get("reply", "")
            gc = compile_grounding(draft_text, obs["kb_results"])
            obs["grounding_check"] = gc
            log("Grounding", (
                f"ratio={gc['grounding_ratio']:.2f} "
                f"safe={gc['auto_reply_safe']} "
                f"ungrounded={gc['ungrounded_claims'][:2]}"
            ))

    return obs


def run_agent(ticket_text: str, ticket_id: str = "T-?", user_id: str = "U-?", memory: AgentMemory = None) -> dict:
    log("Agent", f"ticket={ticket_id} user={user_id} text='{ticket_text[:60]}'")

    if memory is None:
        memory = AgentMemory()

    plan = create_plan(ticket_text, user_id)
    obs = run_tool_loop(ticket_text, ticket_id, user_id, plan, memory)

    result = synthesize(
        ticket_text=ticket_text,
        classification=obs["classification"],
        kb_results=obs["kb_results"],
        history=obs["history"],
        draft=obs["draft"],
        tone=obs["tone"],
        grounding_check=obs.get("grounding_check"),
    )
    result["ticket_id"] = ticket_id

    # ── reflection loop ───────────────────────────────────────────────────────
    iteration = 0
    while result["confidence"] < 0.65 and iteration < MAX_ITER:
        strategy = decide_reflection_strategy(result, iteration)
        if strategy is None:
            break
        iteration += 1
        log("Reflect", f"iter {iteration}/{MAX_ITER} — {strategy['reason']}")

        if strategy["tool"] == "kb_search":
            new_query = f"{strategy['query_modifier']} {ticket_text}"
            new_inp = {"query": new_query.strip(), "top_k": 5}
            r = tool_registry["kb_search"].execute(new_inp)
            if r["success"] and r["data"]:
                obs["kb_results"] = r["data"]
                log("Reflect", f"KB retry found {len(r['data'])} results")
                # re-draft with new KB
                draft_r = tool_registry["draft_reply"].execute(
                    {"ticket_text": ticket_text, "kb_snippets": obs["kb_results"]}
                )
                if draft_r["success"]:
                    obs["draft"] = draft_r["data"]
                    # Re-run grounding compiler with new draft + KB
                    obs["grounding_check"] = compile_grounding(
                        obs["draft"].get("reply", ""), obs["kb_results"]
                    )

        elif strategy["tool"] == "classify_intent":
            r = tool_registry["classify_intent"].execute({"ticket_text": ticket_text})
            if r["success"]:
                obs["classification"] = r["data"]

        result = synthesize(
            ticket_text=ticket_text,
            classification=obs["classification"],
            kb_results=obs["kb_results"],
            history=obs["history"],
            draft=obs["draft"],
            tone=obs["tone"],
            grounding_check=obs.get("grounding_check"),
        )
        result["ticket_id"] = ticket_id
        log("Reflect", f"after iter {iteration}: confidence={result['confidence']}, action={result['action']}")

    # Record this ticket in memory for future dedup
    memory.add_ticket(user_id, {
        "ticket_id": ticket_id,
        "intent": result["intent"],
        "action": result["action"],
    })

    return result
