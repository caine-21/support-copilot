"""
Milestone A smoke test — intent_set decomposition.

All ticket texts loaded from test_tickets.json (source of truth).
Never use hand-written strings — they diverge from actual spec text.
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))

from intent_normalizer import normalize_multi

_TICKET_PATH = os.path.join(os.path.dirname(__file__), 'test_tickets.json')
with open(_TICKET_PATH, encoding='utf-8') as f:
    _TICKETS = {t['id']: t['text'] for t in json.load(f)}


def ticket(tid: str) -> str:
    """Load ticket text from test_tickets.json."""
    return _TICKETS[tid]


CASES = [
    # ── Milestone A target cases ──────────────────────────────────────────────
    # T-031: invoice + SSO broken → intent_set must contain sso_issue (not sso_setup)
    #        sso_issue has no FAQ → partial coverage → score capped → L1
    (ticket("T-031"), ["invoice_download", "sso_issue"], "T-031 (invoice + SSO broken → partial)"),

    # T-017: invoice + cancel → partial coverage (cancel has no FAQ) → L1
    #        (churn Rule 1 still fires in current reasoner → T-017 needs Milestone B)
    #        This test validates intent_set only, not final routing.
    (ticket("T-017"), ["cancel_subscription", "invoice_download"], "T-017 intent_set (cancel+invoice)"),

    # ── SSO ontology: setup vs broken ────────────────────────────────────────
    (ticket("T-012"), ["sso_setup"],  "T-012 (SSO setup with Okta → sso_setup)"),
    (ticket("T-021"), ["sso_setup"],  "T-021 (Azure AD SSO → sso_setup)"),

    # ── Single-intent regressions ─────────────────────────────────────────────
    (ticket("T-001"), ["invoice_download"], "T-001 (invoice download, no refund false-positive)"),
    (ticket("T-002"), ["password_reset"],   "T-002 (password reset)"),
    (ticket("T-003"), ["permission_levels"],"T-003 (permission levels)"),
    (ticket("T-005"), ["data_export"],      "T-005 (data export)"),
    (ticket("T-009"), ["invoice_customize"],"T-009 (VAT invoice customize)"),
    (ticket("T-024"), ["version_history"],  "T-024 (version history beyond 90 days)"),

    # ── reimburse latent bug fix: 'reimbursement' must NOT match refund_eligibility ──
    # T-001 text contains "tax return" not "reimburse", so test with a manual case:
    ("I need my invoice for a reimbursement claim.", ["invoice_download"],
     "reimburse noun → invoice, not refund (latent bug fix)"),
    ("I want a refund, please reimburse me.", ["refund_eligibility"],
     "reimburse me (verb phrase) → refund (correct match)"),
]

print("=" * 70)
print("Milestone A: normalize_multi() intent_set tests (texts from spec)")
print("=" * 70)

all_pass = True
for text, expected_set, label in CASES:
    result = normalize_multi(text)
    got = result["intent_set"]
    ok = set(got) == set(expected_set)
    if not ok:
        all_pass = False
    status = "OK  " if ok else "FAIL"
    print(f"  {status} [{label}]")
    if not ok:
        print(f"       got:      {got}")
        print(f"       expected: {expected_set}")

print()
print("All pass" if all_pass else "FAILURES DETECTED")
