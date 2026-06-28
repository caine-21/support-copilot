"""
Agent loop: hybrid parallel/sequential pipeline.

Phase 1 (parallel):  classify_intent | kb_search | history_lookup
Early exit:          sla_signal or hidden_cancel_signal → ESCALATE_L2 without drafting
Phase 2 (sequential): draft_reply → grounding_compiler → tone_check → synthesize()

Principle: independent data-gathering runs in parallel; generation + verification +
decision stay sequential. Draft is the most expensive step; deterministic signals
(pure regex) can short-circuit it entirely for clear-L2 tickets.
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from concurrent.futures import ThreadPoolExecutor, as_completed

from tools import tool_registry
from reasoner import synthesize, compute_l2_signals, replay_assumptions
from memory import AgentMemory
from grounding_compiler import compile_grounding

DEBUG = True
MAX_ITER = 2


def log(tag: str, msg: str):
    if DEBUG:
        print(f"[{tag}] {msg}")


def _attach_replay(result: dict, ticket_text: str, obs: dict, signals: dict) -> dict:
    """Attach policy-sensitivity replay: which LLM assumptions drive this decision.

    Pure CPU (synthesize does no LLM calls), routing untouched. Probes POLICY
    sensitivity (would the decision change if the model didn't believe X), not
    world causality.
    """
    result["assumption_replay"] = replay_assumptions(
        ticket_text,
        obs.get("classification", {}),
        obs.get("kb_results", []),
        obs.get("history", {}),
        obs.get("draft", {}),
        obs.get("tone", {}),
        grounding_check=obs.get("grounding_check"),
        precomputed_signals=signals,
    )
    return result


def _log_decision(ledger, ticket_id, result, signals, rule):
    """Record the routing decision + its grounds (proximate cause = which signals fired)."""
    fired = [k for k, v in signals.items() if v]
    grounds = list(dict.fromkeys(fired + list(result.get("routing_signals", []))))
    ledger.log_decision(
        ticket_id,
        action=result.get("action"),
        proximate_grounds=grounds,
        inputs={
            "grounding":   result.get("grounding"),
            "churn_risk":  result.get("churn_risk"),
            "tone":        result.get("tone"),
            "intent_set":  result.get("intent_set", []),
            "confidence":  result.get("confidence"),
        },
        rule=rule,
    )


def decide_reflection_strategy(result: dict, iteration: int) -> dict | None:
    """Returns retry strategy dict or None to stop."""
    missing = " ".join(result.get("missing_info", []))
    action = result.get("action", "ESCALATE_L1")

    if action == "ESCALATE_L2":
        return None

    if "no FAQ match" in missing or "no KB grounding" in missing:
        return {
            "tool": "kb_search",
            "reason": "no KB hit on first query — retry with intent-based broader query",
            "query_modifier": "how to help with",
        }

    if "intent ambiguous" in missing:
        return {
            "tool": "classify_intent",
            "reason": "intent was ambiguous — retry classification",
            "query_modifier": "",
        }

    return None


def _phase1_parallel(ticket_text: str, user_id: str, memory: AgentMemory) -> dict:
    """Phase 1: classify_intent + kb_search + history_lookup + tone_check in parallel.

    tone_check is included here (not in Phase 2) so churn_risk is always available,
    even when early L2 exit skips draft_reply.
    """
    obs = {"classification": {}, "kb_results": [], "history": {}, "tone": {}}
    kb_was_cached = [False]  # mutable container for closure

    def _classify():
        r = tool_registry["classify_intent"].execute({"ticket_text": ticket_text})
        return "classification", r.get("data", {}) if r["success"] else {}

    def _kb():
        cached = memory.get_cached_kb(ticket_text)
        if cached is not None:
            log("Memory", f"KB cache hit: {ticket_text[:50]}")
            kb_was_cached[0] = True
            return "kb_results", cached
        r = tool_registry["kb_search"].execute({"query": ticket_text, "top_k": 3})
        return "kb_results", r.get("data", []) if r["success"] else []

    def _history():
        r = tool_registry["history_lookup"].execute({"user_id": user_id, "memory": memory})
        return "history", r.get("data", {}) if r["success"] else {}

    def _tone():
        r = tool_registry["tone_check"].execute({"ticket_text": ticket_text})
        return "tone", r.get("data", {}) if r["success"] else {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futs = [executor.submit(_classify), executor.submit(_kb),
                executor.submit(_history), executor.submit(_tone)]
        for fut in as_completed(futs):
            key, data = fut.result()
            obs[key] = data
            log("Phase1", f"{key} → {str(data)[:80]}")

    if not kb_was_cached[0] and obs["kb_results"]:
        memory.cache_kb(ticket_text, obs["kb_results"])

    return obs


def _phase2_sequential(ticket_text: str, obs: dict) -> dict:
    """Phase 2: draft (expensive LLM) → grounding_compiler (inline)."""
    dr = tool_registry["draft_reply"].execute({
        "ticket_text": ticket_text,
        "kb_snippets": obs["kb_results"],
    })
    if dr["success"]:
        obs["draft"] = dr.get("data", {})
        draft_text = obs["draft"].get("reply", "")
        gc = compile_grounding(draft_text, obs["kb_results"])
        obs["grounding_check"] = gc
        log("Grounding", (
            f"ratio={gc['grounding_ratio']:.2f} "
            f"safe={gc['auto_reply_safe']} "
            f"ungrounded={gc['ungrounded_claims'][:2]}"
        ))

    return obs


def run_agent(ticket_text: str, ticket_id: str = "T-?", user_id: str = "U-?", memory: AgentMemory = None, ledger=None) -> dict:
    log("Agent", f"ticket={ticket_id} user={user_id} text='{ticket_text[:60]}'")

    if memory is None:
        memory = AgentMemory()

    # ── Phase 1: parallel data gathering ─────────────────────────────────────
    obs = _phase1_parallel(ticket_text, user_id, memory)
    obs.update({"draft": {}, "grounding_check": {}})
    if ledger is not None:
        ledger.log_step(ticket_id, "classify_intent", obs["classification"])
        ledger.log_step(ticket_id, "kb_search",       obs["kb_results"])
        ledger.log_step(ticket_id, "history_lookup",  obs["history"])
        ledger.log_step(ticket_id, "tone_check",      obs["tone"])

    # ── Deterministic L2 gate (before expensive draft) ────────────────────────
    signals = compute_l2_signals(ticket_text)
    if ledger is not None:
        ledger.log_step(ticket_id, "l2_signals", signals)
    if signals["sla_signal"] or signals["hidden_cancel_signal"]:
        log("Agent", f"early-L2: sla={signals['sla_signal']} cancel={signals['hidden_cancel_signal']}")
        result = synthesize(
            ticket_text=ticket_text,
            classification=obs["classification"],
            kb_results=obs["kb_results"],
            history=obs["history"],
            draft={},
            tone=obs["tone"],
            grounding_check=None,
            precomputed_signals=signals,
        )
        result["ticket_id"] = ticket_id
        result = _attach_replay(result, ticket_text, obs, signals)
        if ledger is not None:
            _log_decision(ledger, ticket_id, result, signals, rule="early_l2_gate")
        memory.add_ticket(user_id, {"ticket_id": ticket_id, "intent": result["intent"], "action": result["action"]})
        return result

    # ── Phase 2: sequential generation + verification ─────────────────────────
    obs = _phase2_sequential(ticket_text, obs)
    if ledger is not None:
        ledger.log_step(ticket_id, "draft_reply",     obs.get("draft"))
        ledger.log_step(ticket_id, "grounding_check", obs.get("grounding_check"))

    result = synthesize(
        ticket_text=ticket_text,
        classification=obs["classification"],
        kb_results=obs["kb_results"],
        history=obs["history"],
        draft=obs["draft"],
        tone=obs["tone"],
        grounding_check=obs.get("grounding_check"),
        precomputed_signals=signals,
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
            r = tool_registry["kb_search"].execute({"query": new_query.strip(), "top_k": 5})
            if r["success"] and r["data"]:
                obs["kb_results"] = r["data"]
                log("Reflect", f"KB retry found {len(r['data'])} results")
                draft_r = tool_registry["draft_reply"].execute(
                    {"ticket_text": ticket_text, "kb_snippets": obs["kb_results"]}
                )
                if draft_r["success"]:
                    obs["draft"] = draft_r["data"]
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
            precomputed_signals=signals,
        )
        result["ticket_id"] = ticket_id
        log("Reflect", f"after iter {iteration}: confidence={result['confidence']}, action={result['action']}")

    result = _attach_replay(result, ticket_text, obs, signals)
    if ledger is not None:
        _log_decision(ledger, ticket_id, result, signals, rule=f"reflection_iters={iteration}")
    memory.add_ticket(user_id, {
        "ticket_id": ticket_id,
        "intent": result["intent"],
        "action": result["action"],
    })
    return result
