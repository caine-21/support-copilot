"""Diagnose grounding compiler failures for T-054 and T-024."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

r = json.load(open('data/reports/report_v20_draft_fix.json', encoding='utf-8'))
by_id = {c['id']: c for c in r['cases']}

TARGET_IDS = ['T-054', 'T-024']

for tid in TARGET_IDS:
    c = by_id.get(tid)
    if not c:
        print(f"{tid}: NOT FOUND"); continue

    result = c['result']
    gc     = result.get('grounding_check', {})

    print(f"{'='*70}")
    print(f"{tid} — expected={c.get('expected_action')}  got={result['action']}  pass={c['pass']}")
    print(f"  ticket: {c['text'][:100]}")
    print(f"  intent: {result.get('intent')}  grounding={result.get('grounding')}  conf={result.get('confidence')}")
    print()
    print(f"  gc_ratio:        {gc.get('grounding_ratio')}")
    print(f"  auto_reply_safe: {gc.get('auto_reply_safe')}")
    print(f"  ungrounded_summary: {gc.get('ungrounded_summary', '')}")
    print()

    # KB snippets used (from kb_grounding in result)
    kb_snips = result.get('kb_grounding', [])
    print(f"  KB snippets ({len(kb_snips)}):")
    for s in kb_snips:
        print(f"    [{s['doc_id']}]: {s['snippet'][:120]}")
    print()

    # Draft reply
    draft = result.get('draft_reply', '')
    print(f"  Draft reply:")
    print(f"    {draft}")
    print()

    # Claim graph
    claims = gc.get('ungrounded_claims', [])
    print(f"  Ungrounded claims: {claims}")
    print()

    # We need the full claims list — stored in grounding_check
    # Note: eval.py only stores ungrounded_claims in result, not the full claims list
    # So we can only see the ungrounded ones here.
    # The full claims list would require re-running grounding_compiler on this draft.
    print()
