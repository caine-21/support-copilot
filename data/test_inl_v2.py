"""Smoke test for refund_status and invoice_customize rules."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    # Refund status — should NOT be refund_eligibility
    ("I'm expecting a refund of $149 for my subscription.", "refund_status"),
    ("I'm trying to check the status of my refund.", "refund_status"),
    ("I'm waiting for a refund of $149 to be processed.", "refund_status"),
    # Refund policy — still refund_eligibility
    ("I need help understanding your refund policy.", "refund_eligibility"),
    ("When am I eligible for a refund?", "refund_eligibility"),
    ("I want a full refund for this month's subscription.", "refund_eligibility"),
    # Invoice customization
    ("Can we customize our invoice to include our company name?", "invoice_customize"),
    ("We need to customize the invoice with our branding.", "invoice_customize"),
    ("Can I get a VAT invoice? We need to add our VAT number.", "invoice_customize"),
    # Invoice download — plain invoice (no vat customization language)
    ("Hi, how do I download my invoice from last month?", "invoice_download"),
    ("Can I get a VAT invoice for our enterprise subscription?", "invoice_customize"),  # VAT → customize
    ("I need to download my invoice for subscription #85632.", "invoice_download"),
]

all_pass = True
for q, expected_id in CASES:
    r = normalize(q)
    ok = r['intent_id'] == expected_id
    if not ok:
        all_pass = False
    status = "OK  " if ok else "FAIL"
    print(f"  {status} {q[:62]!r:65s} -> {r['intent_id']:25s} (want {expected_id})")

print()
print("All pass" if all_pass else "FAILURES DETECTED")
