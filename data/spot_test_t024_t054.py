"""Spot-test gc fixes on T-024 and T-054 using their actual v20 drafts and full KB snippets."""
import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'agent')
from grounding_compiler import compile_grounding

faqs = json.load(open('data/faq/acme_collab_faq.json', encoding='utf-8'))
by_faq = {f['id']: f for f in faqs}

report = json.load(open('data/reports/report_v20_draft_fix.json', encoding='utf-8'))
by_id  = {c['id']: c for c in report['cases']}

TESTS = [
    {
        'id': 'T-024',
        'faq_id': 'FAQ-feature-07',
        'draft': by_id['T-024']['result']['draft_reply'],
        'expect': 'gc_safe=True (90 days visible in full snippet; meta-claim excluded)',
    },
    {
        'id': 'T-054',
        'faq_id': 'FAQ-troubleshoot-01',
        'draft': by_id['T-054']['result']['draft_reply'],
        'expect': 'gc_safe=True (contact support visible in full snippet)',
    },
]

for t in TESTS:
    faq = by_faq[t['faq_id']]
    # Simulate kb result with full 600-char snippet
    kb = [{'doc_id': faq['id'], 'snippet': faq['answer'][:600]}]

    print(f"=== {t['id']} ===")
    print(f"  draft: {t['draft'][:120]}...")
    print(f"  kb snippet ({len(kb[0]['snippet'])} chars): {kb[0]['snippet'][:80]}...")
    print(f"  expect: {t['expect']}")
    print()

    result = compile_grounding(t['draft'], kb)

    print(f"  gc_ratio:   {result['grounding_ratio']}")
    print(f"  safe:       {result['auto_reply_safe']}")
    print(f"  claims ({len(result['claims'])}):")
    for c in result['claims']:
        tag = 'UNGND' if not c.get('supported_by_kb') else 'OK   '
        print(f"    [{tag}] {c['text'][:80]}")
    print(f"  ungrounded: {result['ungrounded_claims']}")
    verdict = 'PASS' if result['auto_reply_safe'] else 'FAIL'
    print(f"  => {verdict}")
    print()
