import sys, json
sys.stdout.reconfigure(encoding='utf-8')
TARGET = {"policy_inquiry", "settings_change"}
with open("data/test_tickets.json", encoding="utf-8") as f:
    cases = json.load(f)
for c in cases:
    rr = c.get("expected", {}).get("routing_reason", "")
    if rr in TARGET:
        print(f"[{c['id']}] {rr}: {c['text'][:120]}")
