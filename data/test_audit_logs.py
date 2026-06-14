"""Smoke test for audit_logs intent rule (T-020)."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    ("I am trying to set up audit logs but I cannot find the option in Settings. We are on the Team plan.", "audit_logs"),
    ("Where are the audit logs for our workspace?", "audit_logs"),
    ("How do I access the audit trail for user activity?", "audit_logs"),
    ("We need activity logs for compliance.", "audit_logs"),
    ("How do I download my invoice?", "invoice_download"),
    ("Set up SSO with Okta.", "sso_setup"),
]

all_pass = True
for q, want in CASES:
    r = normalize(q)
    ok = r['intent_id'] == want
    if not ok: all_pass = False
    print(f"  {'OK  ' if ok else 'FAIL'} {q[:65]!r:68s} -> {r['intent_id']}")
print()
print("All pass" if all_pass else "FAILURES DETECTED")
