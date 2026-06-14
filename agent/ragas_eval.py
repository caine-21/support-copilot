"""
RAGAS-style Evaluation Layer (P2).

Three metrics computed from an eval report JSON (no re-run needed):

  Retrieval Recall (consistency proxy)
    For each case: expected_faqs = INTENT_FAQ_MAP[intent_set]
    recall = |retrieved ∩ expected| / |expected|
    ⚠️  This measures INL-KB consistency, NOT ground-truth recall.
    (No manual FAQ labels in test_tickets.json; uses INTENT_FAQ_MAP as proxy.)

  Grounding Score
    Distribution of strong/weak/none grounding, broken down by action class.
    Fully deterministic — computed from report fields.

  Faithfulness (LLM-as-judge)
    For AUTO_REPLY cases: does the draft contain only claims supported by KB?
    LLM returns clean/flagged + optional flagged sentence.
    Aggregated into faithfulness_rate and flagged_cases list.

Output: prints to stdout + writes data/eval_reports/<tag>_ragas.json

CLI:
  py agent/ragas_eval.py data/reports/report_v17.json
"""

import sys
import os
import json
import collections
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from llm import call_llm, safe_json_parse
from kb import INTENT_FAQ_MAP


# ── Retrieval Recall ───────────────────────────────────────────────────────────

def compute_retrieval_recall(cases: list[dict]) -> dict:
    """
    Consistency proxy: measures whether INL intent_set → INTENT_FAQ_MAP docs
    are actually retrieved by the KB search step.

    Skips cases where expected_faqs is empty (no FAQ coverage by design).
    Skips cases where intent_set is ['unknown'] or empty.
    """
    recall_scores = []
    skipped_no_faq = 0
    skipped_unknown = 0
    per_case = []

    for c in cases:
        intent_set = c.get("result", {}).get("intent_set", [])
        kb_grounding = c.get("result", {}).get("kb_grounding", [])

        if not intent_set or intent_set == ["unknown"]:
            skipped_unknown += 1
            continue

        # Expected FAQs: union of INTENT_FAQ_MAP entries for all intents in intent_set
        expected_faqs: set[str] = set()
        for intent_id in intent_set:
            faq_list = INTENT_FAQ_MAP.get(intent_id, [])
            expected_faqs.update(faq_list)

        if not expected_faqs:
            # All intents have no FAQ — skip (L1/L2 by design)
            skipped_no_faq += 1
            continue

        retrieved_docs = {r["doc_id"] for r in kb_grounding}
        hit = expected_faqs & retrieved_docs
        recall = len(hit) / len(expected_faqs)
        recall_scores.append(recall)

        per_case.append({
            "id":            c["id"],
            "intent_set":    intent_set,
            "expected_faqs": sorted(expected_faqs),
            "retrieved_docs": sorted(retrieved_docs),
            "hits":          sorted(hit),
            "recall":        round(recall, 3),
        })

    avg_recall = round(sum(recall_scores) / max(len(recall_scores), 1), 3)

    return {
        "metric":        "retrieval_recall",
        "note":          "Consistency proxy (INL→INTENT_FAQ_MAP), not ground-truth recall",
        "avg_recall":    avg_recall,
        "n_scored":      len(recall_scores),
        "skipped_no_faq":     skipped_no_faq,
        "skipped_unknown":    skipped_unknown,
        "per_case":      per_case,
    }


# ── Grounding Score ────────────────────────────────────────────────────────────

def compute_grounding_score(cases: list[dict]) -> dict:
    """
    Distribution of KB grounding levels (strong/weak/none) per action class.
    Fully deterministic — no LLM call.
    """
    by_action: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"strong": 0, "weak": 0, "none": 0}
    )

    for c in cases:
        action    = c.get("result", {}).get("action", "?")
        grounding = c.get("result", {}).get("grounding", "none")
        if grounding in ("strong", "weak", "none"):
            by_action[action][grounding] += 1

    # Flag unsafe AUTO_REPLY: action=AUTO_REPLY without strong grounding
    unsafe = sum(
        v["weak"] + v["none"]
        for k, v in by_action.items()
        if k == "AUTO_REPLY"
    )

    # Overall distribution
    total_strong = sum(v["strong"] for v in by_action.values())
    total_weak   = sum(v["weak"]   for v in by_action.values())
    total_none   = sum(v["none"]   for v in by_action.values())
    n = max(total_strong + total_weak + total_none, 1)

    return {
        "metric": "grounding_score",
        "overall": {
            "strong": total_strong,
            "weak":   total_weak,
            "none":   total_none,
            "strong_pct": round(total_strong / n, 3),
        },
        "by_action":          dict(by_action),
        "unsafe_auto_reply":  unsafe,
    }


# ── Faithfulness (LLM-as-judge) ───────────────────────────────────────────────

_FAITHFULNESS_SYSTEM = """\
You are evaluating whether an AI-generated customer support reply is faithful to
its knowledge-base (KB) sources. The reply should contain ONLY claims supported
by the provided KB excerpts — no invented details, prices, deadlines, or policies.

You receive:
  - ticket: the customer's message
  - draft: the AI's reply
  - kb_excerpts: the KB snippets the reply was grounded on

Evaluate faithfulness and output JSON only:
{
  "faithful": true | false,
  "flagged_sentence": "<first sentence that contains an unsupported claim, or empty string>",
  "reason": "<one-sentence explanation if unfaithful, else empty string>"
}

Be strict: if the draft adds ANY specific detail (number, date, feature name) not in the KB
excerpts, flag it as unfaithful.\
"""


def compute_faithfulness(cases: list[dict]) -> dict:
    """
    LLM-as-judge faithfulness check for AUTO_REPLY cases only.
    Returns per-case verdict + aggregate rate.
    """
    auto_cases = [
        c for c in cases
        if c.get("result", {}).get("action") == "AUTO_REPLY"
        and c.get("result", {}).get("draft_reply")
        and c.get("result", {}).get("kb_grounding")
    ]

    per_case = []
    faithful_count = 0

    for c in auto_cases:
        result  = c.get("result", {})
        ticket  = c.get("text", "")
        draft   = result.get("draft_reply", "")
        kb_snip = "\n\n".join(
            f"[{r['doc_id']}]: {r.get('snippet','')}"
            for r in result.get("kb_grounding", [])
        )

        user_msg = (
            f"Ticket: {ticket}\n\n"
            f"Draft reply:\n{draft}\n\n"
            f"KB excerpts:\n{kb_snip}"
        )

        raw    = call_llm(_FAITHFULNESS_SYSTEM, user_msg)
        parsed = safe_json_parse(raw)

        faithful = bool(parsed.get("faithful", True))
        if faithful:
            faithful_count += 1

        per_case.append({
            "id":               c["id"],
            "faithful":         faithful,
            "flagged_sentence": parsed.get("flagged_sentence", ""),
            "reason":           parsed.get("reason", ""),
        })

    n = max(len(auto_cases), 1)
    return {
        "metric":              "faithfulness",
        "n_auto_reply":        len(auto_cases),
        "faithfulness_rate":   round(faithful_count / n, 3),
        "unfaithful_count":    len(auto_cases) - faithful_count,
        "flagged_cases":       [p for p in per_case if not p["faithful"]],
        "per_case":            per_case,
    }


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_ragas_eval(report_path: str, skip_faithfulness: bool = False) -> dict:
    """
    Compute all three RAGAS-style metrics from an eval report JSON.
    Returns the full ragas_report dict and writes it to data/eval_reports/<tag>_ragas.json.
    """
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    tag   = report.get("tag", "unknown")
    cases = report.get("cases", [])

    print(f"\n{'='*60}")
    print(f"RAGAS EVAL — report={tag}  ({len(cases)} cases)")
    print(f"{'='*60}")

    recall    = compute_retrieval_recall(cases)
    grounding = compute_grounding_score(cases)

    print(f"\n── Retrieval Recall (consistency proxy) ──")
    print(f"  avg recall  : {recall['avg_recall']} ({recall['n_scored']} cases scored)")
    print(f"  skipped (no FAQ coverage): {recall['skipped_no_faq']}")
    print(f"  skipped (unknown intent):  {recall['skipped_unknown']}")

    print(f"\n── Grounding Score ──")
    ov = grounding["overall"]
    print(f"  strong: {ov['strong']}  weak: {ov['weak']}  none: {ov['none']}"
          f"  ({ov['strong_pct']*100:.0f}% strong)")
    print(f"  unsafe AUTO_REPLY (non-strong): {grounding['unsafe_auto_reply']}")
    for action, dist in sorted(grounding["by_action"].items()):
        print(f"  {action:<20}: strong={dist['strong']} weak={dist['weak']} none={dist['none']}")

    if skip_faithfulness:
        faithfulness = {"metric": "faithfulness", "note": "skipped (--no-faithfulness flag)"}
        print(f"\n── Faithfulness ── (skipped)")
    else:
        print(f"\n── Faithfulness (LLM judge, AUTO_REPLY only) ──")
        faithfulness = compute_faithfulness(cases)
        print(f"  rate        : {faithfulness['faithfulness_rate']*100:.0f}%  "
              f"({faithfulness['n_auto_reply'] - faithfulness['unfaithful_count']}"
              f"/{faithfulness['n_auto_reply']} faithful)")
        if faithfulness.get("flagged_cases"):
            print(f"  flagged cases:")
            for fc in faithfulness["flagged_cases"]:
                print(f"    {fc['id']}: {fc['reason']}")

    ragas_report = {
        "tag":              tag,
        "source_report":    os.path.basename(report_path),
        "retrieval_recall": recall,
        "grounding_score":  grounding,
        "faithfulness":     faithfulness,
    }

    # write output
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'eval_reports')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{tag}_ragas.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ragas_report, f, ensure_ascii=False, indent=2)
    print(f"\n[RAGAS] written → {out_path}")
    print("=" * 60)

    return ragas_report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py agent/ragas_eval.py data/reports/report_<tag>.json [--no-faithfulness]")
        sys.exit(1)

    report_path     = sys.argv[1]
    skip_faith      = "--no-faithfulness" in sys.argv
    run_ragas_eval(report_path, skip_faithfulness=skip_faith)
