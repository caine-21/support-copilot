"""Smoke test for v9 intent rules."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    # Permission levels (T-003)
    ("Can you explain the different permission levels? I need to give a contractor read-only access.", "permission_levels"),
    ("What permission levels are there? Can I set view-only access?", "permission_levels"),
    # Data export expansion (T-005)
    ("How do I export a whole Space as a PDF or ZIP?", "data_export"),
    ("I need to export a whole workspace as a zip file.", "data_export"),
    ("Export all my data to a zip.", "data_export"),
    # Feature feedback (T-073)
    ("I need to leave feedback about a feature.", "feature_feedback"),
    ("Can I leave a review for a workspace feature?", "feature_feedback"),
    ("I want to suggest a feature.", "feature_feedback"),
    # Invoice customize VAT number (T-009)
    ("Can I get a VAT invoice? We need to add our VAT number.", "invoice_customize"),
    # Should NOT be affected
    ("How do I download my invoice from last month?", "invoice_download"),
    ("I want a refund for my subscription.", "refund_eligibility"),
    ("I'm waiting for a refund to be processed.", "refund_status"),
    ("How do I reset my password?", "password_reset"),
]

all_pass = True
for q, expected_id in CASES:
    r = normalize(q)
    ok = r['intent_id'] == expected_id
    if not ok:
        all_pass = False
    status = "OK  " if ok else "FAIL"
    print(f"  {status} {q[:68]!r:71s} -> {r['intent_id']:25s} (want {expected_id})")

print()
print("All pass" if all_pass else "FAILURES DETECTED")
