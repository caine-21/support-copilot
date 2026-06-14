"""
Milestone B smoke test — intent-class routing gate.

Validates that intent-class suppresses L2 over-escalation for technical incidents
and billing disputes. All texts loaded from test_tickets.json.

Success criteria:
  Group A (T-006/008/028/029): technical bug → L1, not L2
  Group B (T-017/018):         billing dispute → L1, not L2
  L2 recall:                   adversarial churn cases still → L2
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))

from intent_normalizer import normalize_multi, TECHNICAL_INTENTS, BILLING_INTENTS, CANCEL_INTENTS

_TICKET_PATH = os.path.join(os.path.dirname(__file__), 'test_tickets.json')
with open(_TICKET_PATH, encoding='utf-8') as f:
    _TICKETS = {t['id']: t['text'] for t in json.load(f)}

def ticket(tid: str) -> str:
    return _TICKETS[tid]


def classify_intent_class(text: str) -> dict:
    """Derive intent class flags from ticket text (deterministic, no LLM)."""
    multi = normalize_multi(text)
    intent_set = set(multi.get("intent_set", ["unknown"]))
    return {
        "intent_set":    sorted(intent_set),
        "has_technical": bool(intent_set & TECHNICAL_INTENTS),
        "has_billing":   bool(intent_set & BILLING_INTENTS),
        "has_cancel":    bool(intent_set & CANCEL_INTENTS),
    }


# Format: (ticket_id_or_None, text, expected_flags, label)
CASES = [
    # ── Group A: technical incidents ─────────────────────────────────────────
    # These fail with frustrated+0.4 rule; Milestone B gates them to L1.
    # INL returns "unknown" for these (no keyword rule), so has_technical
    # must be set by the LLM classify_intent "bug" label — tested via E2E eval.
    # Here we test the INL-level flags only.
    (ticket("T-006"),  {"has_technical": False, "has_billing": False, "has_cancel": False},
     "T-006 (app loading — no INL match, LM 'bug' carries has_technical)"),
    (ticket("T-008"),  {"has_technical": False, "has_billing": False, "has_cancel": False},
     "T-008 (doc sync — no INL match, LM 'bug' carries)"),
    (ticket("T-028"),  {"has_technical": False, "has_billing": False, "has_cancel": False},
     "T-028 (export garbled — no INL match, LM 'bug' carries)"),

    # T-029: ui_preferences INL match → has_technical=True from INL
    (ticket("T-029"),  {"has_technical": True,  "has_billing": False, "has_cancel": False},
     "T-029 (Slack notifications → ui_preferences → has_technical=True)"),

    # ── Group B: billing disputes ─────────────────────────────────────────────
    # T-017: cancel + invoice → has_billing=True AND has_cancel=True → gate closed
    (ticket("T-017"),  {"has_technical": False, "has_billing": True, "has_cancel": True},
     "T-017 (invoice + cancel → billing+cancel gate)"),

    # T-018: refund only → has_billing=True, has_cancel=False → threshold 0.6
    (ticket("T-018"),  {"has_technical": False, "has_billing": True, "has_cancel": False},
     "T-018 (refund only → billing gate, threshold 0.6)"),

    # ── L2 recall guard: explicit churn should still reach L2 ─────────────────
    # These have no billing/technical INL match → default rule → still churn_risk≥0.6
    # (L2 routing depends on LLM churn_risk score — tested in E2E eval)
    # Here just check flags are not incorrectly set:
    ("We need to transfer account ownership to our successor company.",
     {"has_technical": False, "has_billing": False, "has_cancel": False},
     "hidden_cancel signal (no INL match → default rule applies)"),

    # ── Regression: SSO setup (not broken) stays account class ───────────────
    (ticket("T-012"),  {"has_technical": False, "has_billing": False, "has_cancel": False},
     "T-012 (SSO setup → sso_setup, not sso_issue → not technical)"),
]

print("=" * 70)
print("Milestone B: intent-class flag tests")
print("=" * 70)

all_pass = True
for text, expected_flags, label in CASES:
    result = classify_intent_class(text)
    ok = all(result[k] == v for k, v in expected_flags.items())
    if not ok:
        all_pass = False
    status = "OK  " if ok else "FAIL"
    print(f"  {status} [{label}]")
    if not ok:
        for k, v in expected_flags.items():
            got = result[k]
            if got != v:
                print(f"       {k}: got {got}, expected {v}  intent_set={result['intent_set']}")

print()
print("Note: T-006/008/028 rely on LM 'bug' label — E2E eval validates full routing.")
print("All pass" if all_pass else "FAILURES DETECTED")
