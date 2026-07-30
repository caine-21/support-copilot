"""Customer Context Beta deterministic evaluation entry point."""

from __future__ import annotations

import hashlib
import json
import copy
import argparse
import datetime as dt
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_loop
from agent_loop import run_agent
from run_ledger import RunLedger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data" / "customer_context_beta_v1.json"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "customer_context_beta_v1.manifest.json"
DEFAULT_CORRECTIONS = PROJECT_ROOT / "data" / "customer_context_beta_v2_oracle_corrections.json"
DEFAULT_V2_MANIFEST = PROJECT_ROOT / "data" / "customer_context_beta_v2.manifest.json"
DEFAULT_EVIDENCE_DIR = PROJECT_ROOT / "data" / "customer_context_beta" / "evidence"
SOURCE_FILES = (
    "agent/customer_context.py",
    "agent/context_guard.py",
    "agent/intent_normalizer.py",
    "agent/reasoner.py",
    "agent/agent_loop.py",
    "agent/tools.py",
    "agent/grounding_compiler.py",
    "agent/customer_context_eval.py",
    "data/customer_context_beta_v1.json",
    "data/customer_context_beta_v1.manifest.json",
    "data/customer_context_beta_v2_oracle_corrections.json",
    "data/customer_context_beta_v2.manifest.json",
)


def load_dataset_contract(
    dataset_path: Path = DEFAULT_DATASET,
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    version: str = "v2",
    corrections_path: Path = DEFAULT_CORRECTIONS,
    v2_manifest_path: Path = DEFAULT_V2_MANIFEST,
) -> dict:
    dataset_bytes = dataset_path.read_bytes()
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    dataset = json.loads(dataset_bytes.decode("utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if dataset_hash != manifest["sha256"]:
        raise ValueError(
            f"dataset hash mismatch: got {dataset_hash}, want {manifest['sha256']}"
        )
    if dataset["dataset_version"] != manifest["dataset_version"]:
        raise ValueError("dataset version does not match manifest")
    if len(dataset["cases"]) != manifest["case_count"]:
        raise ValueError("dataset case count does not match manifest")
    if len({case["case_id"] for case in dataset["cases"]}) != len(dataset["cases"]):
        raise ValueError("dataset contains duplicate case_id values")
    if len({case["ticket_text"] for case in dataset["cases"]}) != len(dataset["cases"]):
        raise ValueError("dataset contains duplicate ticket_text values")

    base_contract = {
        "dataset": dataset,
        "manifest": manifest,
        "dataset_hash": dataset_hash,
        "base_dataset_hash": dataset_hash,
        "oracle_corrections": [],
    }
    if version == "v1":
        return base_contract
    if version != "v2":
        raise ValueError(f"unsupported dataset version: {version}")

    corrections_bytes = corrections_path.read_bytes()
    corrections_hash = hashlib.sha256(corrections_bytes).hexdigest()
    corrections = json.loads(corrections_bytes.decode("utf-8"))
    v2_manifest = json.loads(v2_manifest_path.read_text(encoding="utf-8"))
    combined_hash = hashlib.sha256(
        f"{dataset_hash}\n{corrections_hash}".encode("utf-8")
    ).hexdigest()
    if corrections["parent_dataset_sha256"] != dataset_hash:
        raise ValueError("v2 corrections reference a different v1 dataset hash")
    if corrections_hash != v2_manifest["oracle_corrections_sha256"]:
        raise ValueError("v2 oracle corrections hash mismatch")
    if combined_hash != v2_manifest["combined_sha256"]:
        raise ValueError("v2 combined dataset hash mismatch")

    corrected = copy.deepcopy(dataset)
    by_id = {case["case_id"]: case for case in corrected["cases"]}
    for correction in corrections["oracle_corrections"]:
        case_id = correction["case_id"]
        if case_id not in by_id:
            raise ValueError(f"oracle correction references unknown case: {case_id}")
        for key, value in correction["changes"].items():
            by_id[case_id][key] = copy.deepcopy(value)
    corrected["dataset_version"] = corrections["dataset_version"]
    corrected["oracle_origin"] = v2_manifest["oracle_origin"]
    return {
        "dataset": corrected,
        "manifest": v2_manifest,
        "dataset_hash": combined_hash,
        "base_dataset_hash": dataset_hash,
        "oracle_corrections_hash": corrections_hash,
        "oracle_corrections": corrections["oracle_corrections"],
    }


def resolve_context_fixture(dataset: dict, fixture_id: str, _seen=None) -> dict:
    fixtures = dataset["context_fixtures"]
    if fixture_id not in fixtures:
        raise ValueError(f"unknown context fixture: {fixture_id}")
    seen = set(_seen or ())
    if fixture_id in seen:
        raise ValueError(f"cyclic context fixture inheritance: {fixture_id}")
    seen.add(fixture_id)

    fixture = fixtures[fixture_id]
    if "extends" in fixture:
        resolved = resolve_context_fixture(dataset, fixture["extends"], seen)
    else:
        resolved = {
            "as_of": fixture["as_of"],
            "fields": copy.deepcopy(fixture["fields"]),
        }

    if "as_of" in fixture:
        resolved["as_of"] = fixture["as_of"]
    for field_name, changes in fixture.get("overrides", {}).items():
        if field_name not in resolved["fields"]:
            raise ValueError(f"override references unknown field: {field_name}")
        resolved["fields"][field_name].update(copy.deepcopy(changes))
    return resolved


class _FixedTool:
    def __init__(self, data):
        self.data = data

    def execute(self, _input_data: dict) -> dict:
        return {"success": True, "data": copy.deepcopy(self.data)}


def _source_snapshot() -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    file_hashes = {}
    working_tree_file_hashes = {}
    for relative_path in SOURCE_FILES:
        committed_content = subprocess.run(
            ["git", "show", f"{commit}:{relative_path}"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        working_tree_content = (PROJECT_ROOT / relative_path).read_bytes()
        file_hashes[relative_path] = hashlib.sha256(committed_content).hexdigest()
        working_tree_file_hashes[relative_path] = hashlib.sha256(
            working_tree_content
        ).hexdigest()
    joined = "\n".join(f"{path}:{file_hashes[path]}" for path in sorted(file_hashes))
    snapshot_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    working_tree_joined = "\n".join(
        f"{path}:{working_tree_file_hashes[path]}"
        for path in sorted(working_tree_file_hashes)
    )
    working_tree_snapshot_hash = hashlib.sha256(
        working_tree_joined.encode("utf-8")
    ).hexdigest()

    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    tracked_status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    return {
        "git_commit": commit,
        "working_tree_dirty": bool(status),
        "tracked_working_tree_dirty": bool(tracked_status),
        "source_snapshot_sha256": snapshot_hash,
        "file_sha256": file_hashes,
        "working_tree_source_snapshot_sha256": working_tree_snapshot_hash,
        "working_tree_file_sha256": working_tree_file_hashes,
    }


def _load_kb_documents() -> dict[str, dict]:
    path = PROJECT_ROOT / "data" / "faq" / "acme_collab_faq.json"
    docs = json.loads(path.read_text(encoding="utf-8"))
    return {doc["id"]: doc for doc in docs}


def _routing_observations(case: dict, kb_doc: dict) -> dict:
    routing_fixture = case.get("routing_fixture", "safe_grounded")
    tone = {
        "tone": "neutral",
        "churn_risk": 0.0,
        "urgency": "low",
        "churn_signals": [],
    }
    if routing_fixture == "refund_human_review":
        tone = {
            "tone": "neutral",
            "churn_risk": 0.85,
            "urgency": "medium",
            "churn_signals": ["refund request"],
        }

    answer = kb_doc["answer"]
    draft = answer.split(". ", 1)[0].strip()
    if draft and not draft.endswith("."):
        draft += "."
    grounding_check = {
        "claims": [
            {
                "text": draft,
                "supported_by_kb": True,
                "supporting_doc": kb_doc["id"],
            }
        ],
        "grounding_ratio": 1.0,
        "ungrounded_claims": [],
        "ungrounded_summary": "",
        "auto_reply_safe": True,
    }
    return {
        "classification": {
            "intent": case["classification_intent"],
            "confidence": 0.95,
            "secondary_intent": None,
        },
        "kb_results": [
            {
                "doc_id": kb_doc["id"],
                "snippet": answer,
                "score": 0.95,
            }
        ],
        "history": {"ticket_count": 0, "past_tickets": []},
        "tone": tone,
        "draft": {
            "reply": draft,
            "kb_used": [kb_doc["id"]],
            "grounded": True,
            "gaps": "",
            "grounding_check": grounding_check,
        },
    }


def _registry(observations: dict) -> dict:
    return {
        "classify_intent": _FixedTool(observations["classification"]),
        "kb_search": _FixedTool(observations["kb_results"]),
        "history_lookup": _FixedTool(observations["history"]),
        "tone_check": _FixedTool(observations["tone"]),
        "draft_reply": _FixedTool(observations["draft"]),
    }


def _failure_details(case: dict, result: dict) -> list[str]:
    failures = []
    expected = case["expected"]
    if result.get("action") != expected["route"]:
        failures.append("route_mismatch")
    actual_auto = result.get("action") == "AUTO_REPLY"
    if actual_auto and not expected["auto_reply_allowed"]:
        failures.append("unsafe_auto_reply")
    if result.get("reason_codes", []) != expected["reason_codes"]:
        failures.append("reason_code_mismatch")
    actual_relevant = result.get("customer_context_decision", {}).get("relevant_fields", [])
    if actual_relevant != case["relevant_fields"]:
        failures.append("relevant_field_mismatch")
    return failures


def _decision_fingerprint(result: dict) -> dict:
    context_decision = result.get("customer_context_decision", {})
    return {
        "action": result.get("action"),
        "reason_codes": result.get("reason_codes", []),
        "relevant_fields": context_decision.get("relevant_fields", []),
        "used_fields": context_decision.get("used_fields", []),
        "blocking_fields": context_decision.get("blocking_fields", []),
    }


def _run_cases(contract: dict, source: dict, run_at: str, ledger=None) -> list[dict]:
    dataset = contract["dataset"]
    kb_docs = _load_kb_documents()
    records = []
    for case in dataset["cases"]:
        started = time.perf_counter()
        context = resolve_context_fixture(dataset, case["context_fixture"])
        observations = _routing_observations(case, kb_docs[case["kb_doc_id"]])
        result = run_agent(
            ticket_text=case["ticket_text"],
            ticket_id=case["case_id"],
            user_id="U-synthetic-eval",
            customer_context=context,
            registry=_registry(observations),
            ledger=ledger,
            no_service=True,
        )
        if ledger is not None:
            ledger.log_output(case["case_id"], result)
        failures = _failure_details(case, result)
        context_decision = result.get("customer_context_decision", {})
        records.append({
            "case_id": case["case_id"],
            "scenario_type": case["scenario_type"],
            "dataset_version": dataset["dataset_version"],
            "dataset_hash": contract["dataset_hash"],
            "source_snapshot_sha256": source["source_snapshot_sha256"],
            "git_commit": source["git_commit"],
            "working_tree_dirty": source["working_tree_dirty"],
            "run_at": run_at,
            "run_mode": "deterministic_no_service",
            "provider": "none",
            "ticket_text": case["ticket_text"],
            "customer_context_status": {
                name: {
                    "value": field["value"],
                    "status": field["status"],
                    "source": field["source"],
                    "updated_at": field["updated_at"],
                    "allowed_for_auto_reply": field["allowed_for_auto_reply"],
                }
                for name, field in context["fields"].items()
            },
            "expected_route": case["expected"]["route"],
            "actual_route": result.get("action"),
            "route_matches": result.get("action") == case["expected"]["route"],
            "expected_auto_reply_allowed": case["expected"]["auto_reply_allowed"],
            "actual_auto_reply": result.get("action") == "AUTO_REPLY",
            "erroneous_auto_reply": (
                result.get("action") == "AUTO_REPLY"
                and not case["expected"]["auto_reply_allowed"]
            ),
            "expected_reason_codes": case["expected"]["reason_codes"],
            "reason_codes": result.get("reason_codes", []),
            "expected_relevant_fields": case["relevant_fields"],
            "used_fields": context_decision.get("used_fields", []),
            "blocking_fields": context_decision.get("blocking_fields", []),
            "relevant_fields": context_decision.get("relevant_fields", []),
            "failure_class": failures[0] if failures else None,
            "failures": failures,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "debug": {
                "grounding": result.get("grounding"),
                "intent_set": result.get("intent_set", []),
                "routing_signals": result.get("routing_signals", []),
                "decision_reason": result.get("reason"),
                "context_field_states": context_decision.get("field_states", {}),
            },
        })
    return records


def _summary(records: list[dict], deterministic: bool) -> dict:
    failures = [record for record in records if record["failures"]]
    escalations = [record for record in records if record["actual_route"] != "AUTO_REPLY"]
    scenario_counts = Counter(record["scenario_type"] for record in records)
    scenario_passed = Counter(
        record["scenario_type"] for record in records if not record["failures"]
    )
    exit_checks = {
        "all_30_records_complete": len(records) == 30,
        "missing_fields_never_auto_reply": not any(
            r["actual_auto_reply"] for r in records
            if r["scenario_type"] == "missing_required_field"
        ),
        "conflicting_fields_never_auto_reply": not any(
            r["actual_auto_reply"] for r in records
            if r["scenario_type"] == "conflicting_sources"
        ),
        "stale_fields_never_auto_reply": not any(
            r["actual_auto_reply"] for r in records
            if r["scenario_type"] == "stale_required_field"
        ),
        "ticket_override_never_auto_reply": not any(
            r["actual_auto_reply"] for r in records
            if r["scenario_type"] == "ticket_override_attempt"
        ),
        "existing_high_risk_rules_match": all(
            r["route_matches"] for r in records
            if r["scenario_type"] == "existing_high_risk"
        ),
        "erroneous_auto_reply_zero": not any(r["erroneous_auto_reply"] for r in records),
        "deterministic_repeat_matches": deterministic,
        "every_escalation_has_reason": all(r["reason_codes"] for r in escalations),
        "all_oracles_match": not failures,
    }
    return {
        "total": len(records),
        "passed": len(records) - len(failures),
        "failed": len(failures),
        "route_matches": sum(1 for record in records if record["route_matches"]),
        "auto_reply_count": sum(1 for record in records if record["actual_auto_reply"]),
        "erroneous_auto_reply_count": sum(
            1 for record in records if record["erroneous_auto_reply"]
        ),
        "failure_case_ids": [record["case_id"] for record in failures],
        "failure_class_counts": dict(Counter(
            failure for record in records for failure in record["failures"]
        )),
        "scenario_distribution": {
            key: {"total": count, "passed": scenario_passed[key]}
            for key, count in sorted(scenario_counts.items())
        },
        "exit_checks": exit_checks,
        "exit_criteria_met": all(exit_checks.values()),
    }


def run_fixed_evaluation(
    *,
    write_artifacts: bool = False,
    output_dir: Path = DEFAULT_EVIDENCE_DIR,
    tag: str | None = None,
    dataset_version: str = "v2",
) -> dict:
    contract = load_dataset_contract(version=dataset_version)
    source = _source_snapshot()
    run_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    safe_tag = tag or dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H%M%S%z")
    ledger = None
    if write_artifacts:
        ledger = RunLedger(
            tag=f"customer-context-beta-{safe_tag}",
            base_dir=str(output_dir / "runs"),
            meta={
                "dataset_version": contract["dataset"]["dataset_version"],
                "dataset_hash": contract["dataset_hash"],
                "git_commit": source["git_commit"],
                "source_snapshot_sha256": source["source_snapshot_sha256"],
                "mode": "deterministic_no_service",
                "provider": "none",
            },
        )

    previous_debug = agent_loop.DEBUG
    agent_loop.DEBUG = False
    try:
        first = _run_cases(contract, source, run_at, ledger)
        second = _run_cases(contract, source, run_at, None)
    finally:
        agent_loop.DEBUG = previous_debug

    repeat_mismatches = [
        first_record["case_id"]
        for first_record, second_record in zip(first, second)
        if _decision_fingerprint({
            "action": first_record["actual_route"],
            "reason_codes": first_record["reason_codes"],
            "customer_context_decision": {
                "relevant_fields": first_record["relevant_fields"],
                "used_fields": first_record["used_fields"],
                "blocking_fields": first_record["blocking_fields"],
            },
        }) != _decision_fingerprint({
            "action": second_record["actual_route"],
            "reason_codes": second_record["reason_codes"],
            "customer_context_decision": {
                "relevant_fields": second_record["relevant_fields"],
                "used_fields": second_record["used_fields"],
                "blocking_fields": second_record["blocking_fields"],
            },
        })
    ]
    deterministic = not repeat_mismatches
    report = {
        "schema_version": 1,
        "run": {
            "tag": safe_tag,
            "run_at": run_at,
            "mode": "deterministic_no_service",
            "provider": "none",
            "git_commit": source["git_commit"],
            "working_tree_dirty": source["working_tree_dirty"],
            "tracked_working_tree_dirty": source["tracked_working_tree_dirty"],
            "source_snapshot_sha256": source["source_snapshot_sha256"],
            "source_file_sha256": source["file_sha256"],
            "working_tree_source_snapshot_sha256": (
                source["working_tree_source_snapshot_sha256"]
            ),
            "working_tree_source_file_sha256": source["working_tree_file_sha256"],
        },
        "dataset": {
            "version": contract["dataset"]["dataset_version"],
            "sha256": contract["dataset_hash"],
            "base_v1_sha256": contract["base_dataset_hash"],
            "case_count": len(contract["dataset"]["cases"]),
            "oracle_origin": contract["dataset"]["oracle_origin"],
        },
        "determinism": {
            "repeat_count": 2,
            "decision_mismatch_case_ids": repeat_mismatches,
            "matched": deterministic,
        },
        "summary": _summary(first, deterministic),
        "oracle_corrections": contract["oracle_corrections"],
        "fix_iterations": [
            {
                "iteration": 1,
                "evidence": "2026-07-31-initial-v1",
                "result": "27/30 contract matches; 0 erroneous auto-replies; deterministic repeat matched",
                "failures": ["CCB-001", "CCB-002", "CCB-029"],
            },
            {
                "iteration": 2,
                "change": "Do not consult customer fields after an existing deterministic L2 gate; preserve unknown-intent safety lock and version the affected oracle labels.",
                "dataset": contract["dataset"]["dataset_version"],
            },
        ],
        "evidence_boundary": (
            "Automated tests plus a Codex-assisted deterministic local structured evaluation "
            "over synthetic fixtures. No external support-agent review, real customer data, "
            "Shadow Mode, pilot, production traffic, or business-effect measurement."
        ),
        "cases": first,
    }
    if ledger is not None:
        report["run"]["ledger_dir"] = str(Path(ledger.finalize(report)).relative_to(PROJECT_ROOT))
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"customer_context_beta_{safe_tag}.json"
        md_path = output_dir / f"customer_context_beta_{safe_tag}.md"
        review_path = output_dir / f"developer_review_{safe_tag}.md"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_markdown_report(report), encoding="utf-8")
        review_path.write_text(render_review_form(report), encoding="utf-8")
        report["artifact_paths"] = {
            "json": str(json_path.relative_to(PROJECT_ROOT)),
            "markdown": str(md_path.relative_to(PROJECT_ROOT)),
            "developer_review": str(review_path.relative_to(PROJECT_ROOT)),
        }
    return report


def render_markdown_report(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Customer Context Beta 本地结构化评测",
        "",
        f"- 运行时间：`{report['run']['run_at']}`",
        f"- 基础 commit：`{report['run']['git_commit']}`（working tree dirty：`{str(report['run']['working_tree_dirty']).lower()}`）",
        f"- tracked working tree dirty：`{str(report['run']['tracked_working_tree_dirty']).lower()}`",
        f"- 源码快照 SHA-256：`{report['run']['source_snapshot_sha256']}`",
        f"- 数据版本：`{report['dataset']['version']}`",
        f"- 数据 SHA-256：`{report['dataset']['sha256']}`",
        "- 运行方式：`deterministic_no_service`；provider：`none`",
        f"- Oracle 来源：{report['dataset']['oracle_origin']}",
        "",
        "## 汇总",
        "",
        f"- 场景：{summary['total']} 条；合同一致：{summary['passed']} 条；不一致：{summary['failed']} 条。",
        f"- 路由一致：{summary['route_matches']} / {summary['total']}。",
        f"- 自动回复：{summary['auto_reply_count']} 条；错误自动回复：{summary['erroneous_auto_reply_count']} 条。",
        f"- 重复运行：{report['determinism']['repeat_count']} 次；确定性决策一致：{str(report['determinism']['matched']).lower()}。",
        f"- 达到退出条件：{str(summary['exit_criteria_met']).lower()}。",
        "",
        "## 场景分布",
        "",
        "| 类型 | 总数 | 合同一致 |",
        "|---|---:|---:|",
    ]
    for name, values in summary["scenario_distribution"].items():
        lines.append(f"| `{name}` | {values['total']} | {values['passed']} |")
    lines += [
        "",
        "## 退出条件",
        "",
    ]
    for name, passed in summary["exit_checks"].items():
        lines.append(f"- {'通过' if passed else '未通过'}：`{name}`")
    lines += [
        "",
        "## 失败案例",
        "",
    ]
    failed = [case for case in report["cases"] if case["failures"]]
    if not failed:
        lines.append("本次没有合同不一致案例。")
    else:
        for case in failed:
            lines.append(
                f"- `{case['case_id']}`：expected `{case['expected_route']}`，"
                f"actual `{case['actual_route']}`；失败分类：{', '.join(case['failures'])}。"
            )
    lines += [
        "",
        "## Oracle 修正与修复迭代",
        "",
        f"- Oracle 修正：{len(report['oracle_corrections'])} 条；v1 数据与初次失败报告均保留。",
        f"- 有记录的修复迭代：{len(report['fix_iterations'])} 条。",
        "",
        "## 证据边界",
        "",
        report["evidence_boundary"],
        "",
        "## 可复现命令",
        "",
        "```powershell",
        "cd D:\\ehe\\support-copilot",
        "py -m agent.customer_context_eval --tag <new-tag>",
        "```",
        "",
        "## 尚未验证",
        "",
        "- 开发者人工复核表尚未填写。",
        "- 未经独立客服人员复核。",
        "- 未使用真实客户数据、线上流量或真实 provider 输出。",
        "- 未实施 Shadow Mode、试点、生产运行或 ROI 评估。",
        "",
    ]
    return "\n".join(lines)


def render_review_form(report: dict) -> str:
    preferred = [
        "CCB-001", "CCB-004", "CCB-007", "CCB-012", "CCB-017",
        "CCB-021", "CCB-025", "CCB-028", "CCB-029",
    ]
    by_id = {case["case_id"]: case for case in report["cases"]}
    selected = [by_id[case_id] for case_id in preferred]
    lines = [
        "# Customer Context Beta 开发者人工复核表",
        "",
        "> 状态：待填写。填写前不得声明已完成开发者人工复核或用户验证。",
        "",
        "| Case | 系统决定 | 判断依据 | 我的判断 | 是否接受 | 修改原因 |",
        "|---|---|---|---|---|---|",
    ]
    for case in selected:
        grounds = ", ".join(case["reason_codes"])
        fields = ", ".join(case["blocking_fields"] or case["used_fields"])
        basis = f"{grounds}; fields={fields or 'none'}"
        lines.append(
            f"| `{case['case_id']}` | `{case['actual_route']}` | {basis} |  |  |  |"
        )
    lines += [
        "",
        "本次自动评测没有系统失败案例时，不另造失败案例；如后续运行失败，应把原失败记录加入下一版复核表。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the frozen Customer Context Beta deterministic evaluation."
    )
    parser.add_argument("--tag", default=None, help="Artifact tag; defaults to local timestamp")
    parser.add_argument(
        "--dataset-version",
        choices=("v1", "v2"),
        default="v2",
        help="Frozen dataset contract to run",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_EVIDENCE_DIR,
        help="Evidence output directory",
    )
    args = parser.parse_args()
    report = run_fixed_evaluation(
        write_artifacts=True,
        output_dir=args.output_dir,
        tag=args.tag,
        dataset_version=args.dataset_version,
    )
    print(json.dumps({
        "summary": report["summary"],
        "dataset": report["dataset"],
        "run": report["run"],
        "artifacts": report.get("artifact_paths", {}),
    }, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["exit_criteria_met"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
