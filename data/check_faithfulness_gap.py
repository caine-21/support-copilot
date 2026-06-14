import json, sys
sys.stdout.reconfigure(encoding='utf-8')
r = json.load(open('data/reports/report_v18_gc.json', encoding='utf-8'))
by_id = {c['id']: c for c in r['cases']}

unfaithful_ids = {'T-002','T-005','T-021','T-037','T-042','T-043','T-044','T-046','T-051','T-054','T-082'}

print('=== Unfaithful cases: gc_ratio vs RAGAS flag ===')
for tid in sorted(unfaithful_ids):
    c = by_id.get(tid)
    if not c:
        continue
    gc     = c['result'].get('grounding_check', {})
    ratio  = gc.get('grounding_ratio', 'n/a')
    safe   = gc.get('auto_reply_safe', '?')
    action = c['result']['action']
    ungnd  = gc.get('ungrounded_claims', [])[:1]
    print(f"  {tid}: action={action} gc_ratio={ratio} gc_safe={safe}")
    if ungnd:
        print(f"       gc_ungnd: {ungnd[0][:70]}")

print()
print('=== All AUTO_REPLY cases: gc_ratio distribution ===')
auto = [c for c in r['cases'] if c['result']['action'] == 'AUTO_REPLY']
faithful_count = 0
for c in sorted(auto, key=lambda x: x['result'].get('grounding_check', {}).get('grounding_ratio', 1.0)):
    gc    = c['result'].get('grounding_check', {})
    ratio = gc.get('grounding_ratio', 'n/a')
    flag  = '<-- RAGAS unfaithful' if c['id'] in unfaithful_ids else ''
    if c['id'] not in unfaithful_ids:
        faithful_count += 1
    print(f"  {c['id']}: gc_ratio={ratio} {flag}")

print(f"\nTotal AUTO_REPLY: {len(auto)}")
print(f"RAGAS faithful: {faithful_count}/{len(auto)} = {faithful_count/len(auto):.0%}")
print(f"\nKey question: do unfaithful cases have gc_ratio >= 0.75 (gc said 'safe')?")
ungnd_but_gc_safe = [c for c in auto if c['id'] in unfaithful_ids
                     and c['result'].get('grounding_check', {}).get('auto_reply_safe', True)]
print(f"Unfaithful AND gc_safe=True: {len(ungnd_but_gc_safe)}")
for c in ungnd_but_gc_safe:
    ratio = c['result'].get('grounding_check', {}).get('grounding_ratio', '?')
    print(f"  {c['id']} gc_ratio={ratio}")
