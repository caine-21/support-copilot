"""MCP stdio cold-start diagnostic (A2A-0).

Spawns `agent.support_mcp_server` as a FRESH subprocess N times and measures
only milestones observable through the MCP client protocol:

  client_enter_ms        time to establish the stdio client connection
  initialize_ms          time to complete MCP initialize handshake
  list_tools_ms          time to complete tools/list
  first_tool_call_ms     time to complete one search_knowledge_base call
  shutdown_ms            time to close the session/client
  total_ms               wall time for the whole run

Milestones that are NOT separately observable without modifying the server
protocol (process spawn, python import, server "ready") are reported as
"not_separately_observable" — we do NOT change the protocol to measure them.

Writes a machine-readable summary to <out> (default data/a2/mcp_stdio_diagnostic.json).

Usage: py -B scripts/diagnose_mcp_stdio.py [--runs 20] [--out data/a2/mcp_stdio_diagnostic_before.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PER_RUN_DEADLINE_S = 45.0  # generous cap so we can measure a slow tail, not kill it early


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


async def one_run(idx: int) -> dict:
    started = time.perf_counter()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-u", "-B", "-m", "agent.support_mcp_server"],
        cwd=str(ROOT),
        env=_env(),
    )
    run = {"idx": idx}
    try:
        async with asyncio.timeout(PER_RUN_DEADLINE_S):
            async with stdio_client(params) as (read, write):
                run["client_enter_ms"] = round((time.perf_counter() - started) * 1000, 1)
                t0 = time.perf_counter()
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    run["initialize_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                    t0 = time.perf_counter()
                    tools = await session.list_tools()
                    run["list_tools_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                    run["tool_count"] = len(tools.tools)
                    t0 = time.perf_counter()
                    await session.call_tool(
                        "search_knowledge_base",
                        {"query": "download my invoice", "top_k": 1},
                    )
                    run["first_tool_call_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                t0 = time.perf_counter()
        run["shutdown_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        run["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        run["success"] = True
        run["failure_stage"] = None
    except asyncio.TimeoutError:
        run["success"] = False
        run["failure_stage"] = "run_deadline"
        run["error"] = f"exceeded {PER_RUN_DEADLINE_S}s"
    except Exception as exc:  # noqa: BLE001 — diagnostic must capture any failure
        run["success"] = False
        run["failure_stage"] = type(exc).__name__
        run["error"] = str(exc)[:300]
    return run


def _pct(values, p):
    if not values:
        return None
    return round(sorted(values)[min(len(values) - 1, int(len(values) * p))], 1)


def _stats(key: str, runs: list[dict]):
    vals = [r[key] for r in runs if r.get("success") and r.get(key) is not None]
    if not vals:
        return {"not_separately_observable": True}
    return {"count": len(vals), "p50": _pct(vals, 0.5), "p95": _pct(vals, 0.95),
            "max": round(max(vals), 1), "min": round(min(vals), 1)}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "data" / "a2" / "mcp_stdio_diagnostic.json"))
    args = ap.parse_args()

    runs = []
    for i in range(args.runs):
        runs.append(await one_run(i + 1))

    successes = [r for r in runs if r["success"]]
    metrics = {
        "client_enter_ms": _stats("client_enter_ms", runs),
        "initialize_ms": _stats("initialize_ms", runs),
        "list_tools_ms": _stats("list_tools_ms", runs),
        "first_tool_call_ms": _stats("first_tool_call_ms", runs),
        "shutdown_ms": _stats("shutdown_ms", runs),
        "total_ms": _stats("total_ms", runs),
    }
    not_obs = ["process_spawn_ms", "server_ready_ms", "python_import_ms"]
    for k in not_obs:
        metrics[k] = {"not_separately_observable": True}

    report = {
        "script": "scripts/diagnose_mcp_stdio.py",
        "date": "2026-08-07",
        "n_runs": args.runs,
        "success_count": len(successes),
        "timeout_count": sum(1 for r in runs if r["failure_stage"] == "run_deadline"),
        "failure_count": args.runs - len(successes),
        "failure_stages": {s: sum(1 for r in runs if r["failure_stage"] == s) for s in
                           sorted({r["failure_stage"] for r in runs if not r["success"]})},
        "metrics": metrics,
        "per_run": [{k: r.get(k) for k in ("idx", "success", "client_enter_ms", "initialize_ms",
                                            "list_tools_ms", "first_tool_call_ms", "shutdown_ms",
                                            "total_ms", "failure_stage")} for r in runs],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Console summary (no full stderr / env info)
    print(f"success={len(successes)}/{args.runs} timeout={report['timeout_count']} "
          f"failures={report['failure_count']}")
    for k, v in metrics.items():
        if v.get("not_separately_observable"):
            print(f"  {k}: not_separately_observable")
        else:
            print(f"  {k}: p50={v['p50']} p95={v['p95']} max={v['max']} ms")
    print(f"wrote -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
