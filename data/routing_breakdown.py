"""
Parse eval log output + test_tickets.json → routing_reason breakdown.
No re-run needed.

Usage:
  py data/routing_breakdown.py <path-to-eval-log>

Or pipe eval output:
  py -m agent.eval 2>&1 | py data/routing_breakdown.py /dev/stdin
"""
import sys, os, re, json
sys.stdout.reconfigure(encoding='utf-8')
from collections import defaultdict

DATA_DIR = os.path.dirname(__file__)


def load_cases() -> dict[str, dict]:
    path = os.path.join(DATA_DIR, "test_tickets.json")
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    return {c["id"]: c for c in cases}


def routing_reason(case: dict) -> str:
    rr = case.get("expected", {}).get("routing_reason")
    if rr:
        return rr
    tt = case.get("trigger_type")
    if tt:
        return tt
    return "untagged"


def parse_log(log_text: str) -> dict[str, str]:
    """Return {ticket_id: 'PASS'|'FAIL'}"""
    results = {}
    for m in re.finditer(r"\[(T-\d{3})\] (PASS|FAIL)", log_text):
        results[m.group(1)] = m.group(2)
    return results


def run(log_path: str):
    if log_path == "-" or log_path == "/dev/stdin":
        log_text = sys.stdin.read()
    else:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            log_text = f.read()

    cases   = load_cases()
    results = parse_log(log_text)

    if not results:
        print("[ERROR] No PASS/FAIL entries found in log. Check log path.")
        sys.exit(1)

    # Group by routing_reason
    by_reason: dict[str, list[bool]] = defaultdict(list)
    for tid, verdict in sorted(results.items()):
        case = cases.get(tid)
        if not case:
            continue
        rr = routing_reason(case)
        by_reason[rr].append(verdict == "PASS")

    # Also group by expected action
    by_action: dict[str, list[bool]] = defaultdict(list)
    for tid, verdict in results.items():
        case = cases.get(tid)
        if not case:
            continue
        action = case.get("expected", {}).get("action", "?")
        by_action[action].append(verdict == "PASS")

    L2_REASONS = {"churn_signal", "emotional_escalation", "contract_risk",
                  "security_concern", "hidden_cancel"}

    total = len(results)
    passed = sum(1 for v in results.values() if v == "PASS")

    print(f"\n{'='*58}")
    print(f"ROUTING REASON BREAKDOWN  ({passed}/{total} overall)")
    print(f"{'='*58}")

    print(f"\n── By action class ──")
    for action in ["AUTO_REPLY", "ESCALATE_L1", "ESCALATE_L2"]:
        vals = by_action.get(action, [])
        if not vals:
            continue
        pct = 100 * sum(vals) // len(vals)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"  {action:<20} {bar} {sum(vals)}/{len(vals)} ({pct}%)")

    print(f"\n── By routing reason ──")
    non_l2 = sorted(
        [(rr, v) for rr, v in by_reason.items() if rr not in L2_REASONS and rr != "untagged"],
        key=lambda x: x[0]
    )
    l2_items = sorted(
        [(rr, v) for rr, v in by_reason.items() if rr in L2_REASONS],
        key=lambda x: sum(x[1]) / len(x[1])   # sort by accuracy asc → weakest first
    )
    untagged = by_reason.get("untagged", [])

    for rr, vals in non_l2:
        pct = 100 * sum(vals) // len(vals)
        print(f"  {rr:<28} {sum(vals)}/{len(vals)} ({pct}%)")

    if untagged:
        pct = 100 * sum(untagged) // len(untagged)
        print(f"  {'(manual/untagged)':<28} {sum(untagged)}/{len(untagged)} ({pct}%)")

    print(f"\n  ── L2 trigger types (weakest → strongest) ──")
    for rr, vals in l2_items:
        pct = 100 * sum(vals) // len(vals)
        flag = " ⚠" if pct < 70 else ""
        print(f"  {rr:<28} {sum(vals)}/{len(vals)} ({pct}%){flag}")

    print(f"\n{'='*58}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py data/routing_breakdown.py <log-file>")
        sys.exit(1)
    run(sys.argv[1])
