import json, sys
sys.stdout.reconfigure(encoding='utf-8')
r = json.load(open('data/reports/report_v20_draft_fix.json', encoding='utf-8'))

print(f"OVERALL: {r['summary']['passed']}/{r['summary']['total']} ({r['summary']['pct']}%)")

baseline = [c for c in r['cases'] if not c.get('attack_type')]
adv      = [c for c in r['cases'] if c.get('attack_type')]
print(f"BASELINE {sum(1 for c in baseline if c['pass'])}/{len(baseline)}")
print(f"ADV      {sum(1 for c in adv if c['pass'])}/{len(adv)}")

l2_exp = [c for c in r['cases'] if c.get('expected_action') == 'ESCALATE_L2']
l2_hit = [c for c in l2_exp if c['result']['action'] == 'ESCALATE_L2']
print(f"L2 recall: {len(l2_hit)}/{len(l2_exp)} = {len(l2_hit)/max(len(l2_exp),1):.0%}")

auto = [c for c in r['cases'] if c['result']['action'] == 'AUTO_REPLY']
print(f"AUTO_REPLY count: {len(auto)}")

fails = [(c['id'], c.get('expected_action'), c['result']['action'],
          c['result'].get('grounding_check', {}).get('grounding_ratio', '?'))
         for c in r['cases'] if not c['pass']]
print(f"\nFAILURES ({len(fails)}):")
for fid, exp, got, ratio in fails:
    print(f"  {fid}: expected={exp} got={got} gc_ratio={ratio}")

gc_blocked = [c for c in r['cases']
              if c['result'].get('grounding_check', {}).get('auto_reply_safe') is False]
print(f"\nGC blocked (auto_reply_safe=False): {len(gc_blocked)}")
for c in gc_blocked:
    gc = c['result']['grounding_check']
    print(f"  {c['id']}: ratio={gc['grounding_ratio']} pass={c['pass']}")
