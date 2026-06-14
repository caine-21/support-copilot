"""Verify snippet truncation as root cause for T-024 and T-054."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

faqs = json.load(open('data/faq/acme_collab_faq.json', encoding='utf-8'))
by_id = {f['id']: f for f in faqs}

for faq_id, label in [('FAQ-feature-07', 'T-024'), ('FAQ-troubleshoot-01', 'T-054')]:
    faq = by_id[faq_id]
    ans = faq['answer']
    print(f"=== {faq_id} ({label}) ===")
    print(f"Full answer length: {len(ans)} chars")
    print(f"[:300] cutoff point: ...{repr(ans[290:310])}...")
    print(f"[:300] ends at: '{ans[295:300]}'")
    print()
    print(f"What GC receives ([:300]):")
    print(f"  {ans[:300]}")
    print()
    print(f"What GC MISSES (300+):")
    print(f"  {ans[300:]}")
    print()
    # Find key facts
    for key in ['90 days', 'Team plan', 'Enterprise', 'contact support', 'support@']:
        pos = ans.find(key)
        if pos >= 0:
            status = 'VISIBLE to GC' if pos < 300 else 'HIDDEN from GC (truncated)'
            print(f"  '{key}' at char {pos}: {status}")
    print()
