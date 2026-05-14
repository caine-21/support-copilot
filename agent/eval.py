"""
Eval harness: 20 test tickets with expected outcomes.
Run: python -m agent.eval

Metrics reported:
  - Intent accuracy
  - Action accuracy (end-to-end)
  - KB grounding coverage (auto-reply tickets)
  - Escalation precision / recall
  - L2 recall (did we catch all high-risk tickets)
"""
import sys
import os
import json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import agent_loop
from agent_loop import run_agent
from memory import AgentMemory


def load_test_cases() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'test_tickets.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def score_case(result: dict, expected: dict) -> tuple[bool, list[str]]:
    failures = []

    # intent check (if specified)
    if "intent" in expected:
        got = result.get("intent", "")
        want = expected["intent"]
        if got != want:
            failures.append(f"intent: got '{got}', want '{want}'")

    # action check (if specified)
    if "action" in expected:
        got = result.get("action", "")
        want = expected["action"]
        if got != want:
            failures.append(f"action: got '{got}', want '{want}'")

    # min_confidence check
    if "min_confidence" in expected:
        got = result.get("confidence", 0)
        want = expected["min_confidence"]
        if got < want:
            failures.append(f"confidence {got:.2f} < min {want:.2f}")

    # tone check (if specified)
    if "tone" in expected:
        got = result.get("tone", "")
        want = expected["tone"]
        if got != want:
            failures.append(f"tone: got '{got}', want '{want}'")

    # churn_risk min (if specified)
    if "churn_risk_min" in expected:
        got = result.get("churn_risk", 0)
        want = expected["churn_risk_min"]
        if got < want:
            failures.append(f"churn_risk {got:.2f} < min {want:.2f}")

    # missing_info non-empty check
    if expected.get("missing_info_nonempty"):
        mi = result.get("missing_info", [])
        if not mi:
            failures.append("missing_info should be non-empty but is empty")

    # AUTO_REPLY must have strong grounding — weak/none is unsafe
    if result.get("action") == "AUTO_REPLY":
        if result.get("grounding") != "strong":
            failures.append(f"AUTO_REPLY with grounding={result.get('grounding')} — unsafe (strong required)")
        if not result.get("kb_grounding"):
            failures.append("AUTO_REPLY without any kb_grounding")

    return len(failures) == 0, failures


def compute_metrics(results: list[dict], cases: list[dict], tag: str = "") -> dict:
    n = len(cases)

    intent_correct = sum(
        1 for r, c in zip(results, cases)
        if "intent" in c["expected"] and r["intent"] == c["expected"]["intent"]
    )
    intent_total = sum(1 for c in cases if "intent" in c["expected"])

    action_correct = sum(
        1 for r, c in zip(results, cases)
        if "action" in c["expected"] and r["action"] == c["expected"]["action"]
    )
    action_total = sum(1 for c in cases if "action" in c["expected"])

    # KB grounding coverage for AUTO_REPLY cases
    auto_cases = [(r, c) for r, c in zip(results, cases) if r.get("action") == "AUTO_REPLY"]
    grounded_auto = sum(1 for r, _ in auto_cases if r.get("kb_grounding"))
    kb_grounding_rate = grounded_auto / max(len(auto_cases), 1)

    # L2 recall: of expected L2 tickets, how many did we correctly escalate to L2?
    l2_expected = [(r, c) for r, c in zip(results, cases) if c["expected"].get("action") == "ESCALATE_L2"]
    l2_correct = sum(1 for r, _ in l2_expected if r.get("action") == "ESCALATE_L2")
    l2_recall = l2_correct / max(len(l2_expected), 1)

    # False L2: auto-reply cases wrongly escalated to L2
    auto_expected = [(r, c) for r, c in zip(results, cases) if c["expected"].get("action") == "AUTO_REPLY"]
    false_l2 = sum(1 for r, _ in auto_expected if r.get("action") == "ESCALATE_L2")
    false_escalation_rate = false_l2 / max(len(auto_expected), 1)

    # Unsafe AUTO_REPLY: auto-replied without strong KB grounding
    all_auto = [r for r in results if r.get("action") == "AUTO_REPLY"]
    unsafe_auto = sum(1 for r in all_auto if r.get("grounding") != "strong")
    unsafe_auto_rate = unsafe_auto / max(len(all_auto), 1)

    return {
        "intent_accuracy":        round(intent_correct / max(intent_total, 1), 2),
        "action_accuracy":        round(action_correct / max(action_total, 1), 2),
        "kb_grounding_coverage":  round(kb_grounding_rate, 2),
        "l2_recall":              round(l2_recall, 2),
        "false_escalation_rate":  round(false_escalation_rate, 2),
        "unsafe_auto_reply_rate": round(unsafe_auto_rate, 2),
        "total_cases":            n,
    }


def run_eval():
    cases = load_test_cases()
    baseline = [c for c in cases if not c.get("attack_type")]
    adversarial = [c for c in cases if c.get("attack_type")]

    print("=" * 70)
    print(f"SUPPORT COPILOT EVAL — {len(cases)} total ({len(baseline)} baseline + {len(adversarial)} adversarial)")
    print("=" * 70)

    agent_loop.DEBUG = False
    memory = AgentMemory()

    passed = 0
    results_list = []

    for tc in cases:
        ticket_id = tc["id"]
        user_id   = tc["user_id"]
        text      = tc["text"]
        expected  = tc["expected"]
        difficulty = tc.get("difficulty", "?")

        try:
            result = run_agent(ticket_id=ticket_id, ticket_text=text, user_id=user_id, memory=memory)
        except Exception as e:
            print(f"\n[{ticket_id}] ERROR: {e}")
            results_list.append({"intent": "error", "action": "error", "confidence": 0, "kb_grounding": []})
            continue

        results_list.append(result)
        ok, failures = score_case(result, expected)
        status = "PASS" if ok else "FAIL"
        note = tc.get("note", "")

        print(f"\n[{ticket_id}] {status} ({difficulty}) — {text[:55]}...")
        print(f"  intent={result['intent']} action={result['action']} conf={result['confidence']:.2f} tone={result['tone']}")
        if note:
            print(f"  note: {note}")
        for f in failures:
            print(f"  ✗ {f}")
        if ok:
            passed += 1

    # split results
    base_results = results_list[:len(baseline)]
    adv_results  = results_list[len(baseline):]

    base_metrics = compute_metrics(base_results, baseline)
    adv_metrics  = compute_metrics(adv_results, adversarial) if adversarial else {}

    base_passed = sum(1 for r, c in zip(base_results, baseline) if score_case(r, c["expected"])[0])
    adv_passed  = sum(1 for r, c in zip(adv_results, adversarial) if score_case(r, c["expected"])[0]) if adversarial else 0

    def _pct(m, key): return f"{m.get(key, 0)*100:.0f}%"

    print("\n" + "=" * 70)
    print(f"OVERALL: {passed}/{len(cases)} passed ({100 * passed // len(cases)}%)")
    print("=" * 70)

    print(f"\n── BASELINE (T-001–T-020): {base_passed}/{len(baseline)} passed ──")
    print(f"  Action accuracy        : {_pct(base_metrics,'action_accuracy')}")
    print(f"  L2 recall              : {_pct(base_metrics,'l2_recall')}   ← safety gate")
    print(f"  Unsafe AUTO_REPLY rate : {_pct(base_metrics,'unsafe_auto_reply_rate')}   ← hallucination risk")
    print(f"  False escalation rate  : {_pct(base_metrics,'false_escalation_rate')}")

    if adv_metrics:
        adv_by_type = {"A": [], "B": [], "C": []}
        for r, c in zip(adv_results, adversarial):
            t = c.get("attack_type", "?")
            ok, _ = score_case(r, c["expected"])
            adv_by_type.setdefault(t, []).append(ok)

        print(f"\n── ADVERSARIAL (T-021–T-035): {adv_passed}/{len(adversarial)} passed ──")
        print(f"  Action accuracy        : {_pct(adv_metrics,'action_accuracy')}")
        print(f"  L2 recall              : {_pct(adv_metrics,'l2_recall')}   ← safety gate")
        print(f"  Unsafe AUTO_REPLY rate : {_pct(adv_metrics,'unsafe_auto_reply_rate')}   ← hallucination risk")
        print(f"  False escalation rate  : {_pct(adv_metrics,'false_escalation_rate')}")
        for attack_type, results in sorted(adv_by_type.items()):
            n = len(results)
            p = sum(results)
            label = {"A": "KB misleading", "B": "Emotional noise", "C": "Multi-intent"}[attack_type]
            print(f"  [{attack_type}] {label:<20}: {p}/{n} passed")
    print("=" * 70)

    return passed == len(cases)


if __name__ == "__main__":
    success = run_eval()
    sys.exit(0 if success else 1)
