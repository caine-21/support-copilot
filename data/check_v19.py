import json, sys
sys.stdout.reconfigure(encoding='utf-8')

v18 = json.load(open('data/reports/report_v18_gc.json', encoding='utf-8'))
v19 = json.load(open('data/reports/report_v19_gc2.json', encoding='utf-8'))
ragas = json.load(open('data/eval_reports/v19_gc2_ragas.json', encoding='utf-8'))

a18 = {c['id']: c for c in v18['cases'] if c['result']['action'] == 'AUTO_REPLY'}
a19 = {c['id']: c for c in v19['cases'] if c['result']['action'] == 'AUTO_REPLY'}

print(f"=== AUTO_REPLY pool: v18={len(a18)}  v19={len(a19)} ===")
removed = sorted(set(a18) - set(a19))
added   = sorted(set(a19) - set(a18))
print(f"Removed (GC downgraded v18→v19): {removed}")
print(f"Added to AUTO (was blocked/L1 in v18): {added}")
for tid in removed:
    gc = a18[tid]['result'].get('grounding_check', {})
    print(f"  {tid}: v18 gc_ratio={gc.get('grounding_ratio')} safe={gc.get('auto_reply_safe')}")

print()
faith = ragas.get('faithfulness', {})
print(f"=== Faithfulness v19_gc2: {faith.get('rate')} ({faith.get('faithful_count')}/{faith.get('total_count')}) ===")
flagged = faith.get('flagged_cases', [])
print(f"Flagged (unfaithful) cases: {len(flagged)}")
for c in flagged:
    cid = c.get('id', '?')
    sent = c.get('flagged_sentence', '')[:90]
    # Check if still AUTO_REPLY in v19 (expected) and what GC ratio is
    v19c = next((x for x in v19['cases'] if x['id'] == cid), None)
    gc_ratio = v19c['result'].get('grounding_check', {}).get('grounding_ratio', '?') if v19c else '?'
    gc_safe  = v19c['result'].get('grounding_check', {}).get('auto_reply_safe', '?') if v19c else '?'
    print(f"  {cid}: gc_ratio={gc_ratio} gc_safe={gc_safe}")
    if sent:
        print(f"    flagged: {sent}")
