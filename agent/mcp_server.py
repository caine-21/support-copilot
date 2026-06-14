"""
MCP Server: support-copilot evaluation tools (P3).

Exposes two MCP tools:
  review_latest_regression()
      Finds the two most recent eval reports in data/reports/,
      computes compare_reports() diff, and narrates it with review_regression().

  query_failure_trends(n=5)
      Loads the last N eval reports, tracks per-ticket pass/fail history,
      classifies each failing ticket as PERSISTENT or FLAKY, and returns a
      ranked list (most consistently failing first).

Run:
  py agent/mcp_server.py           — stdio transport (for Claude Desktop / any MCP client)
  mcp dev agent/mcp_server.py      — inspect with MCP dev UI

Add to Claude Desktop config (~/.claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "support-copilot-eval": {
        "command": "py",
        "args": ["D:/ehe/support-copilot/agent/mcp_server.py"]
      }
    }
  }
"""

import sys
import os
import json
import glob as _glob
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server import FastMCP
from regression import compare_reports, review_regression

mcp = FastMCP(
    name="support-copilot-eval",
    instructions=(
        "Tools for reviewing support-copilot eval regressions and failure trends. "
        "Use review_latest_regression() after running py -m agent.eval <tag>. "
        "Use query_failure_trends(n) to identify persistent vs flaky failures."
    ),
)

_REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'reports')


def _list_reports_by_time() -> list[str]:
    """Return report JSON paths sorted by modification time, newest last."""
    pattern = os.path.join(_REPORTS_DIR, "report_*.json")
    paths = _glob.glob(pattern)
    return sorted(paths, key=os.path.getmtime)


# ── Tool 1: review_latest_regression ─────────────────────────────────────────

@mcp.tool()
def review_latest_regression() -> str:
    """
    Compare the two most recent eval reports and return a markdown regression narrative.

    Finds report_*.json files in data/reports/ sorted by modification time,
    takes the two most recent, runs a deterministic field-level diff, then uses
    an LLM to narrate the most important regressions and their likely root causes.

    Returns a markdown report string:
      - Summary (score change, counts)
      - Per-regression: severity, ticket ID, what changed, root cause
      - Recommendations
    """
    reports = _list_reports_by_time()
    if len(reports) < 2:
        return (
            "⚠️  Need at least 2 eval reports to compare.\n"
            f"Found {len(reports)} in {_REPORTS_DIR}.\n"
            "Run: `py -m agent.eval <tag>` twice to generate reports."
        )

    old_path = reports[-2]
    new_path = reports[-1]

    diff = compare_reports(old_path, new_path)

    # Build header
    old_s = diff["old_summary"]
    new_s = diff["new_summary"]
    header = (
        f"## Regression Diff: `{diff['old_tag']}` → `{diff['new_tag']}`\n"
        f"Score: **{old_s.get('pct')}%** → **{new_s.get('pct')}%** "
        f"({old_s.get('passed')}/{old_s.get('total')} → {new_s.get('passed')}/{new_s.get('total')})\n"
        f"Regressions: {len(diff['regressions'])}  |  "
        f"Fixes: {len(diff['fixes'])}  |  "
        f"Stable failures: {len(diff['stable_fails'])}\n\n"
    )

    if not diff["regressions"] and not diff["stable_fails"]:
        return header + "✅ No regressions found."

    narrative = review_regression(diff)
    return header + narrative


# ── Tool 2: query_failure_trends ──────────────────────────────────────────────

@mcp.tool()
def query_failure_trends(n: int = 5) -> str:
    """
    Analyze the last N eval reports to identify persistent vs flaky failures.

    A ticket is PERSISTENT if it fails in all N recent runs (likely a true gap).
    A ticket is FLAKY if it fails in some but not all runs (likely LLM non-determinism).

    Returns a ranked markdown table of failing tickets with:
      - Fail rate across N runs
      - Classification: PERSISTENT / FLAKY
      - Most recent action and expected action
      - Routing signals pattern
    """
    reports = _list_reports_by_time()
    if not reports:
        return f"⚠️  No eval reports found in {_REPORTS_DIR}."

    selected = reports[-n:] if len(reports) >= n else reports
    actual_n = len(selected)

    # Accumulate per-ticket results
    ticket_history: dict[str, dict] = {}

    for path in selected:
        with open(path, encoding="utf-8") as f:
            report = json.load(f)
        tag = report.get("tag", os.path.basename(path))

        for c in report.get("cases", []):
            tid = c["id"]
            if tid not in ticket_history:
                ticket_history[tid] = {
                    "id":              tid,
                    "text":            c.get("text", "")[:80],
                    "expected_action": c.get("expected_action"),
                    "fail_runs":       [],
                    "pass_runs":       [],
                    "actions_seen":    [],
                    "signals_seen":    [],
                }
            th = ticket_history[tid]
            if c.get("pass"):
                th["pass_runs"].append(tag)
            else:
                th["fail_runs"].append(tag)
                th["actions_seen"].append(c.get("result", {}).get("action"))
                th["signals_seen"].extend(c.get("result", {}).get("routing_signals", []))

    # Filter to failing tickets and classify
    failing = [
        th for th in ticket_history.values()
        if th["fail_runs"]
    ]

    for th in failing:
        fail_rate = len(th["fail_runs"]) / actual_n
        th["fail_rate"] = round(fail_rate, 2)
        th["classification"] = "PERSISTENT" if fail_rate >= 1.0 else "FLAKY"

    # Sort: PERSISTENT first, then by fail_rate desc
    failing.sort(key=lambda t: (-int(t["classification"] == "PERSISTENT"), -t["fail_rate"]))

    if not failing:
        return f"✅ No failures across last {actual_n} eval runs (of {len(reports)} total)."

    lines = [
        f"## Failure Trends — last {actual_n} eval runs\n",
        f"{'ID':<8} {'Class':<12} {'Fail rate':<12} {'Expected':<15} {'Typical action'}",
        f"{'─'*8} {'─'*12} {'─'*12} {'─'*15} {'─'*20}",
    ]

    for th in failing:
        typical_action = (
            max(set(th["actions_seen"]), key=th["actions_seen"].count)
            if th["actions_seen"] else "?"
        )
        signals = sorted(set(th["signals_seen"])) or ["(none)"]
        lines.append(
            f"{th['id']:<8} {th['classification']:<12} "
            f"{th['fail_rate']*100:.0f}% ({len(th['fail_runs'])}/{actual_n})  "
            f"{th['expected_action'] or '?':<15} {typical_action}"
        )
        if th["fail_runs"] and th["classification"] == "FLAKY":
            lines.append(f"         signals seen: {', '.join(signals)}")
        lines.append(f"         {th['text'][:75]}")

    persistent_count = sum(1 for t in failing if t["classification"] == "PERSISTENT")
    flaky_count      = sum(1 for t in failing if t["classification"] == "FLAKY")
    lines.append(f"\n**{persistent_count} PERSISTENT** (always fail), **{flaky_count} FLAKY** (sometimes fail)")

    return "\n".join(lines)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
