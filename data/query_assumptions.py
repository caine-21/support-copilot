"""
Query the epistemic layer of an eval report.

Answers: "which decisions hold only because the model believed an LLM assumption?"
This is a VIEW over report_<tag>.json — it reads the assumption_trace / replay
fields emitted by reasoner.py + eval.py. No model calls.

Usage:
    py query_assumptions.py [tag] [--action AUTO_REPLY] [--highrisk]

Examples:
    py query_assumptions.py latest --action AUTO_REPLY --highrisk
    py query_assumptions.py churn-v1
"""
import sys
import os
import json

sys.stdout.reconfigure(encoding="utf-8")


def load_report(tag: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "reports", f"report_{tag}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def query(tag: str, action: str | None = None, highrisk_only: bool = False) -> list[dict]:
    report = load_report(tag)
    hits = []
    for c in report.get("cases", []):
        r = c.get("result", {})
        if r.get("assumption_verdict") != "assumption_driven":
            continue
        if action and r.get("action") != action:
            continue
        if highrisk_only and r.get("assumption_risk") != "high":
            continue
        hits.append({
            "id": c["id"],
            "action": r.get("action"),
            "risk": r.get("assumption_risk"),
            "load_bearing": r.get("load_bearing_assumptions", []),
            "text": c.get("text", "")[:70],
        })
    return hits


def main():
    args = sys.argv[1:]
    positional = [a for a in args if not a.startswith("--")]
    # strip the value that follows --action from positionals
    if "--action" in args:
        action_val = args[args.index("--action") + 1] if args.index("--action") + 1 < len(args) else None
        positional = [a for a in positional if a != action_val]
    tag = positional[0] if positional else "latest"
    action = None
    if "--action" in args:
        action = args[args.index("--action") + 1]
    highrisk = "--highrisk" in args

    hits = query(tag, action=action, highrisk_only=highrisk)

    filt = []
    if action:
        filt.append(f"action={action}")
    if highrisk:
        filt.append("risk=high")
    filt_s = (" [" + ", ".join(filt) + "]") if filt else ""
    print(f"assumption_driven decisions in report_{tag}.json{filt_s}: {len(hits)}")
    for h in hits:
        print(f"  {h['id']:<8} {h['action']:<12} risk={h['risk']:<5} "
              f"load-bearing={h['load_bearing']}  | {h['text']}")


if __name__ == "__main__":
    main()
