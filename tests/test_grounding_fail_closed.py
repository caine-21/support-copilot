"""
Grounding authorization must fail closed (Commit 1).

Principle: unknown grounding state must never authorize AUTO_REPLY.

  - empty draft / empty KB evidence   -> UNKNOWN -> AUTO forbidden
  - empty claims from provider        -> UNKNOWN -> AUTO forbidden (no vacuous truth)
  - provider/compiler exception       -> ERROR   -> AUTO forbidden (+ observable)
  - grounding_check missing / {} / malformed -> UNKNOWN -> AUTO forbidden
  - valid strong grounding            -> SUPPORTED -> AUTO remains eligible (positive control)

These tests exercise the real functions (compile_grounding / synthesize),
not new helpers.
"""

from unittest import mock

import pytest

from agent.grounding_compiler import compile_grounding, GROUNDING_REQUIRED
from agent.reasoner import synthesize


# ── compile_grounding: F1 — empty input ─────────────────────────────────────

def test_empty_draft_fails_closed():
    gc = compile_grounding("", [{"doc_id": "FAQ-x", "snippet": "snippet"}])
    assert gc["grounding_ratio"] == 0.0
    assert gc["auto_reply_safe"] is False
    assert gc.get("reason_code") == "empty_draft_or_kb"


def test_empty_kb_fails_closed():
    gc = compile_grounding("Draft reply with a claim.", [])
    assert gc["grounding_ratio"] == 0.0
    assert gc["auto_reply_safe"] is False
    assert gc.get("reason_code") == "empty_draft_or_kb"


# ── compile_grounding: F2 — empty claims (no vacuous truth) ────────────────

def test_empty_claims_fail_closed():
    with mock.patch("llm.call_llm", return_value='{"claims": []}'):
        gc = compile_grounding(
            "Draft reply with a claim.",
            [{"doc_id": "FAQ-x", "snippet": "snippet"}],
        )
    assert gc["grounding_ratio"] == 0.0
    assert gc["auto_reply_safe"] is False
    assert gc.get("reason_code") == "empty_claims"


def test_malformed_response_fail_closed():
    # safe_json_parse returns {} -> claims [] -> must not become ratio 1.0
    with mock.patch("llm.call_llm", return_value="definitely not json {"):
        gc = compile_grounding(
            "Draft reply with a claim.",
            [{"doc_id": "FAQ-x", "snippet": "snippet"}],
        )
    assert gc["grounding_ratio"] == 0.0
    assert gc["auto_reply_safe"] is False


# ── compile_grounding: E1 — provider exception ─────────────────────────────

def test_provider_exception_fails_closed():
    def _boom(*_a, **_k):
        raise RuntimeError("provider down")

    with mock.patch("llm.call_llm", side_effect=_boom):
        gc = compile_grounding(
            "Draft reply with a claim.",
            [{"doc_id": "FAQ-x", "snippet": "snippet"}],
        )
    assert gc["auto_reply_safe"] is False
    assert gc["grounding_ratio"] == 0.0
    assert gc.get("reason_code") == "compiler_exception"


# ── compile_grounding: normal path preserved (positive control) ────────────

def test_compile_normal_path_preserved():
    payload = '{"claims": [{"text": "a claim", "supported_by_kb": true, "supporting_doc": "FAQ-x"}]}'
    with mock.patch("llm.call_llm", return_value=payload):
        gc = compile_grounding(
            "Draft reply with a claim.",
            [{"doc_id": "FAQ-x", "snippet": "snippet"}],
        )
    assert gc["grounding_ratio"] >= GROUNDING_REQUIRED
    assert gc["auto_reply_safe"] is True


# ── compile_grounding: no_service empty graph ──────────────────────────────

def test_no_service_empty_graph_not_auto():
    gc = compile_grounding(
        "zzz qqq", [{"doc_id": "FAQ-x", "snippet": "invoice"}], no_service=True
    )
    assert gc["grounding_ratio"] == 0.0
    assert gc["auto_reply_safe"] is False


# ── synthesize: F3 / F4 — missing / empty / malformed grounding_check ──────

# A fixture that is otherwise fully eligible for AUTO_REPLY (strong KB,
# high intent confidence, neutral tone, known intent, no high-risk signal).
_STRONG = dict(
    ticket_text="How do I download my invoice?",
    classification={"intent": "invoice_download", "confidence": 0.95},
    kb_results=[{"doc_id": "FAQ-invoice", "snippet": "Download invoices from Billing.", "score": 0.95}],
    history={"ticket_count": 0},
    draft={"reply": "Download invoices from Billing."},
    tone={"tone": "neutral", "churn_risk": 0.0, "urgency": "low", "churn_signals": []},
)


def test_missing_grounding_check_not_auto():
    r = synthesize(**_STRONG, grounding_check=None, no_service=True)
    assert r["action"] != "AUTO_REPLY"


def test_empty_grounding_dict_not_auto():
    r = synthesize(**_STRONG, grounding_check={}, no_service=True)
    assert r["action"] != "AUTO_REPLY"


def test_malformed_grounding_not_auto():
    # auto_reply_safe / grounding_ratio absent -> must not be dict-truthy
    r = synthesize(**_STRONG, grounding_check={"unexpected": 1}, no_service=True)
    assert r["action"] != "AUTO_REPLY"


def test_valid_strong_grounding_still_allows_auto():
    # Positive control: valid strong grounding must still permit AUTO_REPLY.
    r = synthesize(
        **_STRONG,
        grounding_check={"grounding_ratio": 0.85, "auto_reply_safe": True, "ungrounded_claims": []},
        no_service=True,
    )
    assert r["action"] == "AUTO_REPLY"
