import json, sys
sys.stdout.reconfigure(encoding='utf-8')
r = json.load(open('data/reports/report_v18_gc.json', encoding='utf-8'))

print('=== v18_gc RESULTS ===')
print('summary:', r['summary'])
print()

baseline = [c for c in r['cases'] if not c.get('attack_type')]
adv      = [c for c in r['cases'] if c.get('attack_type')]
base_pass = sum(1 for c in baseline if c['pass'])
adv_pass  = sum(1 for c in adv if c['pass'])

print(f'BASELINE {base_pass}/{len(baseline)}  ADV {adv_pass}/{len(adv)}')

l2_exp = [c for c in r['cases'] if c.get('expected_action') == 'ESCALATE_L2']
l2_hit = [c for c in l2_exp if c['result']['action'] == 'ESCALATE_L2']
print(f'L2 recall: {len(l2_hit)}/{len(l2_exp)} = {len(l2_hit)/max(len(l2_exp),1):.0%}')

auto   = [c for c in r['cases'] if c['result']['action'] == 'AUTO_REPLY']
unsafe = [c for c in auto if c['result']['grounding'] != 'strong']
print(f'AUTO_REPLY count: {len(auto)}  unsafe: {len(unsafe)}')
print()

fails = [(c['id'], c['expected_action'], c['result']['action'],
          c['result'].get('grounding_check', {}).get('grounding_ratio', '?'))
         for c in r['cases'] if not c['pass']]
print(f'FAILURES ({len(fails)}):')
for fid, exp, got, ratio in fails:
    print(f'  {fid}: expected={exp} got={got} gc_ratio={ratio}')

print()
gc_blocked = [c for c in r['cases']
              if c['result'].get('grounding_check', {}).get('auto_reply_safe') is False]
print(f'Grounding compiler blocked (auto_reply_safe=False): {len(gc_blocked)}')
for c in gc_blocked:
    gc = c['result']['grounding_check']
    print(f"  {c['id']}: ratio={gc['grounding_ratio']} ungnd={gc['ungrounded_claims'][:2]}")
