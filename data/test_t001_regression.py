"""Verify T-001 and T-003 INL routing is correct after v10 changes."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    # T-001 text from test_tickets.json
    ("Hi, how do I download my invoice from last month? I need it for my tax return.", "invoice_download"),
    # T-002
    ("How do I reset my password? I forgot it and can't log in.", "password_reset"),
    # T-003
    ("Can you explain the different permission levels? I need to give a contractor read-only access.", "permission_levels"),
    # Must not match refund_eligibility or any billing rule
    ("I need my invoice for my tax return.", "invoice_download"),
    ("How do I download my invoice?", "invoice_download"),
]

all_pass = True
for q, want in CASES:
    r = normalize(q)
    ok = r['intent_id'] == want
    if not ok: all_pass = False
    print(f"  {'OK  ' if ok else 'FAIL'} {q[:65]!r:68s} -> {r['intent_id']:25s} (want {want})")
print()
print("All pass" if all_pass else "FAILURES DETECTED")
