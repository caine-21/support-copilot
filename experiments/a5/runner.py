"""A5 experiment runner.

Runs Lane A/B/C over the frozen benchmark, interleaved by case (to reduce
provider drift), scores against the frozen oracle, and saves per-case results
and a summary JSON. No side effects, no executor, no key material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.a5.contracts import ExperimentResult  # noqa: E402
from experiments.a5.metrics import (  # noqa: E402
    category_success,
    load_benchmark,
    load_decision_policy,
    score_result,
    totals,
)
from experiments.a5.lane_a import lane_a  # noqa: E402
from experiments.a5.lane_b import lane_b  # noqa: E402
from experiments.a5.lane_c import lane_c  # noqa: E402


def _benchmark_hash(benchmark: dict) -> str:
    payload = json.dumps(benchmark, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _policy_hash(policy: dict) -> str:
    payload = json.dumps(policy, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _run_case(case: dict) -> list[ExperimentResult]:
    results = []
    for lane_fn, label in ((lane_a, "A"), (lane_b, "B"), (lane_c, "C")):
        try:
            results.append(lane_fn(case))
        except Exception as exc:  # noqa: BLE001 — record lane failure, keep the run going
            results.append(ExperimentResult(
                case_id=case["case_id"], lane=label,
                error_codes=[f"lane_exception:{type(exc).__name__}:{str(exc)[:80]}"],
            ))
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "experiments" / "a5" / "results" / "run_a5.json"))
    ap.add_argument("--interleave", action="store_true", default=True)
    args = ap.parse_args()

    benchmark = load_benchmark()
    policy = load_decision_policy()
    provider = "deepseek"
    model = "deepseek-chat"

    print(f"benchmark_hash={_benchmark_hash(benchmark)} policy_hash={_policy_hash(policy)}")
    print(f"provider={provider} model={model} cases={len(benchmark['cases'])}")

    all_results: list[ExperimentResult] = []
    started = time.monotonic()
    for i, case in enumerate(benchmark["cases"], 1):
        per_case = _run_case(case)
        bm = load_benchmark()
        for r in per_case:
            r.task_success = score_result(bm, r)
        all_results.extend(per_case)
        if i % 5 == 0 or i == len(benchmark["cases"]):
            print(f"  {i}/{len(benchmark['cases'])} cases done")
    elapsed_s = round(time.monotonic() - started, 1)

    by_lane = {lane: [r for r in all_results if r.lane == lane] for lane in ("A", "B", "C")}
    summary = {
        "run_id": "run_a5",
        "provider": provider,
        "model": model,
        "benchmark_hash": _benchmark_hash(benchmark),
        "decision_policy_hash": _policy_hash(policy),
        "elapsed_s": elapsed_s,
        "lanes": {lane: totals(rs) for lane, rs in by_lane.items()},
        "subsets": {lane: category_success(benchmark, rs) for lane, rs in by_lane.items()},
        "per_case": [r.model_dump() for r in all_results],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote -> {out}")

    # console overview
    print("\n=== overall task_success ===")
    for lane, rs in by_lane.items():
        t = totals(rs)
        print(f"  lane {lane}: success={t['task_success']} unsafe_auto={t['unsafe_auto']} "
              f"model_calls/case={t['model_calls_per_case']} tool_calls/case={t['tool_calls_per_case']} "
              f"lat_p50={t['latency_p50_ms']}ms p95={t['latency_p95_ms']}ms")
    print("\n=== multi-intent subset ===")
    mi = category_success(benchmark, all_results).get("multi", {})
    for lane in ("A", "B", "C"):
        lane_mi = category_success(benchmark, by_lane[lane]).get("multi", {})
        print(f"  lane {lane}: multi success={lane_mi.get('rate')} ({lane_mi.get('passed')}/{lane_mi.get('total')})")


if __name__ == "__main__":
    main()
