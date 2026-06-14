"""Quick test for version_history intent."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    ("Can I extend version history beyond 90 days? We need to keep 1 year for compliance.", "version_history"),
    ("How do I restore a previous version of a document?", "version_history"),
    ("I want to restore an old version of my document.", "version_history"),
    ("I accidentally deleted a document.", "unknown"),  # accidental delete ≠ version history
    ("How do I download my invoice?", "invoice_download"),  # no regression
]

all_pass = True
for q, want in CASES:
    r = normalize(q)
    ok = r['intent_id'] == want
    if not ok: all_pass = False
    print(f"  {'OK  ' if ok else 'FAIL'} {q[:70]!r:73s} -> {r['intent_id']}")
print()
print("All pass" if all_pass else "FAILURES DETECTED")
