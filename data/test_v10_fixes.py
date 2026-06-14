"""Verify T-009 and T-070 INL fixes for v10."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    # T-009: "vat invoice" → invoice_customize (not invoice_download)
    ("Can I get a VAT invoice for our enterprise subscription?", "invoice_customize"),
    ("Can I get a VAT invoice? We need to add our VAT number.", "invoice_customize"),
    # T-070: "how to cancel" → cancel_subscription
    ("I'm not sure how to cancel my Team plan subscription.", "cancel_subscription"),
    ("How do I cancel my subscription?", "cancel_subscription"),
    # No regressions on plain invoice download
    ("How do I download my invoice?", "invoice_download"),
    ("I need to download invoice #85632.", "invoice_download"),
    ("Please send me a receipt for last month.", "invoice_download"),
    # cancel_fee guard — should NOT match cancel_subscription
    ("Is there a cancellation fee if I end early?", "cancellation_fee"),
    # cancel_subscription still works
    ("I want to cancel my subscription.", "cancel_subscription"),
    ("I need to cancel my plan.", "cancel_subscription"),
]

all_pass = True
for q, want in CASES:
    r = normalize(q)
    ok = r['intent_id'] == want
    if not ok: all_pass = False
    print(f"  {'OK  ' if ok else 'FAIL'} {q[:65]!r:68s} -> {r['intent_id']:25s} (want {want})")
print()
print("All pass" if all_pass else "FAILURES DETECTED")
