import sys, json
sys.stdout.reconfigure(encoding='utf-8')
with open('data/test_tickets.json', encoding='utf-8') as f:
    cases = json.load(f)
for c in cases:
    if c.get('trigger_type') == 'contract_risk':
        exp = c.get('expected', {})
        crmin = exp.get('churn_risk_min', 'N/A')
        print(f"[{c['id']}] churn_risk_min={crmin}: {c['text'][:90]}")
