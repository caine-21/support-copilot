"""
Regression Reviewer Agent (P1).

Two entry points:
  compare_reports(old_path, new_path) -> dict
      Deterministic field-level diff between two eval JSON reports.
      Identifies regressions (PASS→FAIL), fixes (FAIL→PASS), and stable failures.

  review_regression(diff, old_report, new_report) -> str
      LLM narration: feeds the structured diff to an LLM that explains
      the most important regressions and their likely root causes.

CLI:
  py -m agent.regression data/reports/report_v17.json data/reports/report_v17b.json
"""

import sys
import os
import json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from llm import call_llm


# ── field comparators ──────────────────────────────────────────────────────────

_COMPARE_FIELDS = [
    "action",
    "grounding",
    "routing_signals",   # list → compare sorted
    "confidence",        # float → round to 2dp
    "intent",
]

def _field_changed(old_result: dict, new_result: dict) -> list[dict]:
    """Return list of {field, old, new} for fields that changed."""
    changes = []
    for f in _COMPARE_FIELDS:
        ov = old_result.get(f)
        nv = new_result.get(f)
        # normalise lists for comparison
        if isinstance(ov, list):
            ov = sorted(ov)
        if isinstance(nv, list):
            nv = sorted(nv)
        # normalise floats
        if isinstance(ov, float):
            ov = round(ov, 2)
        if isinstance(nv, float):
            nv = round(nv, 2)
        if ov != nv:
            changes.append({"field": f, "old": ov, "new": nv})
    return changes


# ── compare_reports ────────────────────────────────────────────────────────────

def compare_reports(old_path: str, new_path: str) -> dict:
    """
    Deterministic diff between two eval reports.

    Returns:
      {
        "regressions":   [...],   PASS→FAIL
        "fixes":         [...],   FAIL→PASS
        "stable_fails":  [...],   FAIL in both
        "stable_pass":   int,     count of PASS in both
        "metric_delta":  {...},   new - old for each metric key
        "old_summary":   {...},
        "new_summary":   {...},
      }
    Each regression/fix record:
      { id, text, expected_action, old: {...}, new: {...}, fields_changed: [...] }
    """
    with open(old_path, encoding="utf-8") as f:
        old = json.load(f)
    with open(new_path, encoding="utf-8") as f:
        new = json.load(f)

    old_by_id = {c["id"]: c for c in old["cases"]}
    new_by_id = {c["id"]: c for c in new["cases"]}

    regressions  = []
    fixes        = []
    stable_fails = []
    stable_pass  = 0

    for tid, nc in sorted(new_by_id.items()):
        oc = old_by_id.get(tid)
        if oc is None:
            continue  # new case not in old report — skip

        old_pass = oc.get("pass", False)
        new_pass = nc.get("pass", False)

        changes = _field_changed(oc.get("result", {}), nc.get("result", {}))

        record = {
            "id":              tid,
            "text":            nc.get("text", "")[:120],
            "expected_action": nc.get("expected_action"),
            "routing_reason":  nc.get("routing_reason"),
            "old": {
                "pass":            old_pass,
                "action":          oc.get("result", {}).get("action"),
                "grounding":       oc.get("result", {}).get("grounding"),
                "routing_signals": oc.get("result", {}).get("routing_signals", []),
                "confidence":      round(oc.get("result", {}).get("confidence", 0), 2),
                "failures":        oc.get("failures", []),
            },
            "new": {
                "pass":            new_pass,
                "action":          nc.get("result", {}).get("action"),
                "grounding":       nc.get("result", {}).get("grounding"),
                "routing_signals": nc.get("result", {}).get("routing_signals", []),
                "confidence":      round(nc.get("result", {}).get("confidence", 0), 2),
                "failures":        nc.get("failures", []),
            },
            "fields_changed": changes,
        }

        if old_pass and not new_pass:
            regressions.append(record)
        elif not old_pass and new_pass:
            fixes.append(record)
        elif not old_pass and not new_pass:
            stable_fails.append(record)
        else:
            stable_pass += 1

    # metric delta — compute from per-case data to avoid stored-metrics schema drift
    def _pct_pass(cases_list):
        n = len(cases_list)
        return round(sum(1 for c in cases_list if c.get("pass", False)) / max(n, 1), 3)

    def _l2_recall(cases_list):
        l2_exp = [c for c in cases_list if c.get("expected_action") == "ESCALATE_L2"]
        l2_hit = [c for c in l2_exp if c.get("result", {}).get("action") == "ESCALATE_L2"]
        return round(len(l2_hit) / max(len(l2_exp), 1), 3)

    old_cases = old.get("cases", [])
    new_cases = new.get("cases", [])
    metric_delta = {
        "pass_rate":  round(_pct_pass(new_cases) - _pct_pass(old_cases), 3),
        "l2_recall":  round(_l2_recall(new_cases) - _l2_recall(old_cases), 3),
    }

    return {
        "old_tag":      old.get("tag", "?"),
        "new_tag":      new.get("tag", "?"),
        "old_summary":  old.get("summary", {}),
        "new_summary":  new.get("summary", {}),
        "regressions":  regressions,
        "fixes":        fixes,
        "stable_fails": stable_fails,
        "stable_pass":  stable_pass,
        "metric_delta": metric_delta,
    }


# ── review_regression ──────────────────────────────────────────────────────────

_REVIEW_SYSTEM = """\
You are a regression analyst for an AI support-ticket routing system.

The system routes tickets to: AUTO_REPLY / ESCALATE_L1 / ESCALATE_L2.
Key invariants:
  - L2 recall must be 100% (never miss a high-risk ticket)
  - Unsafe AUTO_REPLY rate must be 0% (never auto-reply without KB grounding)

You receive a structured diff between two eval runs (old → new).
For each regression (PASS→FAIL), identify:
  1. What changed (action, grounding, routing_signals, confidence)
  2. Most likely root cause:
     - LLM_NONDETERMINISM — only LLM-produced fields changed (churn_risk, confidence) with no signal/grounding change
     - SIGNAL_FLIP — a deterministic signal (sla_signal, competitor_exit) appeared/disappeared
     - GROUNDING_CHANGE — KB grounding level changed (strong→weak or weak→none)
     - CODE_REGRESSION — action changed in a way that looks intentional/systematic
  3. Severity:
     - CRITICAL — safety invariant violated (L2→AUTO or grounding=none→AUTO)
     - HIGH — L2 recall dropped (expected L2 got L1 or AUTO)
     - MEDIUM — L1/AUTO swap (over- or under-escalation)
     - LOW — non-action field mismatch (confidence, tone)

Output a concise markdown report:
  ## Regression Report: <old_tag> → <new_tag>
  ### Summary (1-3 sentences)
  ### Regressions (<N>)
  One bullet per regression — [SEVERITY] T-XXX: root cause in 1 sentence.
  ### Fixes (<N>) (if any)
  ### Recommendation (1-2 sentences)

Be direct and specific. Reference ticket IDs and field values.\
"""


def review_regression(diff: dict, max_regressions: int = 10) -> str:
    """
    LLM narration of the regression diff.

    Takes the structured diff dict from compare_reports().
    Returns a markdown report string.
    max_regressions: cap how many regression details to send to LLM (avoid token overflow).
    """
    top_regressions = diff.get("regressions", [])[:max_regressions]
    top_stable_fails = diff.get("stable_fails", [])[:5]

    payload = {
        "old_tag":      diff["old_tag"],
        "new_tag":      diff["new_tag"],
        "old_summary":  diff["old_summary"],
        "new_summary":  diff["new_summary"],
        "metric_delta": diff["metric_delta"],
        "regressions":  top_regressions,
        "fixes":        diff.get("fixes", [])[:5],
        "stable_fails": top_stable_fails,
    }

    user_msg = f"Regression diff:\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    raw = call_llm(_REVIEW_SYSTEM, user_msg)
    # LLM sometimes wraps output in {"report": "..."} — extract if so
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "report" in parsed:
            return parsed["report"]
    except (json.JSONDecodeError, ValueError):
        pass
    return raw


# ── CLI ────────────────────────────────────────────────────────────────────────

def _print_diff_summary(diff: dict):
    old_s = diff["old_summary"]
    new_s = diff["new_summary"]
    print(f"\n{'='*60}")
    print(f"REGRESSION DIFF: {diff['old_tag']} → {diff['new_tag']}")
    print(f"  Score: {old_s.get('pct')}% → {new_s.get('pct')}%  "
          f"({old_s.get('passed')}/{old_s.get('total')} → {new_s.get('passed')}/{new_s.get('total')})")
    print(f"  Regressions (PASS→FAIL): {len(diff['regressions'])}")
    print(f"  Fixes (FAIL→PASS):       {len(diff['fixes'])}")
    print(f"  Stable failures:         {len(diff['stable_fails'])}")
    print(f"  Stable pass:             {diff['stable_pass']}")

    if diff["regressions"]:
        print(f"\n── Regressions ──")
        for r in diff["regressions"]:
            changes_str = "; ".join(
                f"{c['field']}: {c['old']}→{c['new']}"
                for c in r["fields_changed"]
            ) or "(no field change — possibly new failure criteria)"
            print(f"  {r['id']}: {changes_str}")
            print(f"    expected={r['expected_action']}, "
                  f"was={r['old']['action']}, now={r['new']['action']}")

    if diff["fixes"]:
        print(f"\n── Fixes ──")
        for f in diff["fixes"]:
            print(f"  {f['id']}: {f['old']['action']} → {f['new']['action']}")

    if diff["stable_fails"]:
        print(f"\n── Stable failures (in both) ──")
        for sf in diff["stable_fails"]:
            print(f"  {sf['id']}: expected={sf['expected_action']}, "
                  f"got={sf['new']['action']}")

    delta = diff["metric_delta"]
    sig_delta = {k: v for k, v in delta.items() if abs(v) >= 0.01}
    if sig_delta:
        print(f"\n── Significant metric changes (|Δ|≥0.01) ──")
        for k, v in sorted(sig_delta.items()):
            sign = "+" if v > 0 else ""
            print(f"  {k:<30} {sign}{v:.3f}")

    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: py -m agent.regression <old_report.json> <new_report.json>")
        sys.exit(1)

    old_path = sys.argv[1]
    new_path  = sys.argv[2]

    diff = compare_reports(old_path, new_path)
    _print_diff_summary(diff)

    if diff["regressions"] or diff["stable_fails"]:
        print("\n── LLM Review ──")
        narrative = review_regression(diff)
        print(narrative)
    else:
        print("\nNo regressions found. No LLM review needed.")
