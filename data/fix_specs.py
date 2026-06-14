import sys, json
sys.stdout.reconfigure(encoding='utf-8')
with open('data/test_tickets.json', encoding='utf-8') as f:
    cases = json.load(f)

TARGET = {
    'T-047': 'ambiguous update request',
    'T-048': 'too vague / wrong plan name',
    'T-049': 'non-standard third-party account request',
}
for c in cases:
    if c['id'] in TARGET and c['expected'].get('action') == 'AUTO_REPLY':
        rr = c['expected'].get('routing_reason', 'how_to_request')
        c['expected'] = {'action': 'ESCALATE_L1', 'routing_reason': rr}
        print(f"Fixed {c['id']}: AUTO_REPLY -> ESCALATE_L1 ({TARGET[c['id']]})")

with open('data/test_tickets.json', 'w', encoding='utf-8') as f:
    json.dump(cases, f, ensure_ascii=False, indent=2)

# Final tally
with open('data/test_tickets.json', encoding='utf-8') as f:
    final = json.load(f)
from collections import Counter
actions = Counter(c['expected']['action'] for c in final if 'action' in c.get('expected', {}))
print('Final distribution:', dict(actions))
