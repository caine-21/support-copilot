"""
Run Ledger — append-only, immutable record of one eval run.

Philosophy (the whole point):
  The ledger holds *what happened* — semantics suspended. It NEVER holds
  judgments (pass/fail/metrics). Those are a derived VIEW (report.json),
  regenerable and disposable. A broken metric is then a bug in the view,
  never a false fact welded into the permanent record.

  This is the fix for two diseases:
    1. amnesia      — old behaviour was overwritten on every run (report_<tag>.json, "w").
                      Run dirs are immutable; only a mutable `latest.txt` pointer moves.
    2. correct-but-not-true — a structurally-valid-but-meaningless number
                      (e.g. intent_accuracy=0) could sit in the record unnoticed.
                      Now the record only stores raw observations; judgments are
                      recomputed from them.

Layout:
  data/runs/<run_id>/
    meta.json        — run identity + config (one object)
    steps.jsonl      — every pipeline step, append-only  ← the replayable unit
    outputs.jsonl    — per-case final parsed result, append-only
    decisions.jsonl  — per-case routing decision + its grounds, append-only
    report.json      — DERIVED view (scores/metrics), regenerable from the above

run_id = <UTC timestamp>__<tag>__<short hash>  — sortable, human-readable, unique.

NOTE (part b): steps.jsonl currently stores each step's parsed *observation*
(recoverable today at the agent_loop layer). The fields prompt / raw_response /
model_id are reserved slots, filled once the tool/provider layer is instrumented.
"""
import os
import json
import uuid
import datetime


def _utc_now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


class RunLedger:
    def __init__(self, tag: str = "latest", base_dir: str = None, meta: dict = None):
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        safe_tag = (tag or "latest").strip().replace("/", "-").replace(" ", "_") or "latest"
        self.run_id = f"{ts}__{safe_tag}__{uuid.uuid4().hex[:6]}"
        self.tag = safe_tag

        self.base = base_dir or os.path.join(os.path.dirname(__file__), "..", "data", "runs")
        self.dir = os.path.join(self.base, self.run_id)
        os.makedirs(self.dir, exist_ok=True)

        # append-only handles
        self._steps     = open(os.path.join(self.dir, "steps.jsonl"),     "a", encoding="utf-8")
        self._outputs   = open(os.path.join(self.dir, "outputs.jsonl"),   "a", encoding="utf-8")
        self._decisions = open(os.path.join(self.dir, "decisions.jsonl"), "a", encoding="utf-8")

        self.meta = {
            "run_id":         self.run_id,
            "tag":            self.tag,
            "started_utc":    ts,
            "schema_version": 1,
            **(meta or {}),
        }
        self._write_meta()

    # ── internals ────────────────────────────────────────────────────────────
    def _write_meta(self):
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)

    def _append(self, fh, record: dict):
        line = {"run_id": self.run_id, "ts": _utc_now(), **record}
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        fh.flush()

    # ── append-only writers ──────────────────────────────────────────────────
    def log_step(self, ticket_id: str, step: str, observation,
                 *, prompt=None, raw_response=None, model_id=None):
        # prompt / raw_response / model_id: reserved for part (b) — tool/provider layer.
        self._append(self._steps, {
            "ticket_id":    ticket_id,
            "step":         step,
            "observation":  observation,
            "prompt":       prompt,
            "raw_response": raw_response,
            "model_id":     model_id,
        })

    def log_output(self, ticket_id: str, result: dict):
        self._append(self._outputs, {"ticket_id": ticket_id, "result": result})

    def log_decision(self, ticket_id: str, *, action, proximate_grounds, inputs, rule=None):
        self._append(self._decisions, {
            "ticket_id":         ticket_id,
            "action":            action,
            "proximate_grounds": proximate_grounds,  # which signals fired (the WHAT)
            "inputs":            inputs,             # grounding/churn_risk/tone/intent_set/confidence
            "rule":              rule,               # early_l2_gate / reflection_iters=N
        })

    def log_tool_execution(self, ticket_id: str, *, turn_index, call_id, tool_name,
                           backend, redacted_arguments, result_status, evidence,
                           latency_ms, retry_count, authorization_result=None,
                           stop_reason=None):
        """Auditable tool event; raw model reasoning and customer values are omitted."""
        self._append(self._steps, {"ticket_id": ticket_id, "step": "tool_execution",
            "turn_index": turn_index, "call_id": call_id, "tool_name": tool_name,
            "backend": backend, "redacted_arguments": redacted_arguments,
            "result_status": result_status, "evidence_refs": evidence,
            "latency_ms": latency_ms, "retry_count": retry_count,
            "authorization_result": authorization_result, "stop_reason": stop_reason})

    # ── derived view (disposable, regenerable) ───────────────────────────────
    def finalize(self, report_view: dict) -> str:
        self.meta["finished_utc"] = _utc_now()
        self._write_meta()
        with open(os.path.join(self.dir, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report_view, f, ensure_ascii=False, indent=2)
        for fh in (self._steps, self._outputs, self._decisions):
            fh.close()
        # mutable pointer to "most recent" — immutable history lives in the run dirs
        with open(os.path.join(self.base, "latest.txt"), "w", encoding="utf-8") as f:
            f.write(self.run_id + "\n")
        return self.dir
