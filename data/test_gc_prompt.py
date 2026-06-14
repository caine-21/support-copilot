"""Spot-test grounding compiler on RAGAS-unfaithful cases from v18_gc."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'agent')
from grounding_compiler import compile_grounding

TESTS = [
    {
        "id": "T-037",
        "draft": ("Thank you for reaching out! Your invoice for the renewal is available in "
                  "Settings → Billing → Invoice History. Invoices are automatically emailed "
                  "to the billing contact on file on renewal dates. If you need any additional "
                  "help, please let me know."),
        "kb": [{"doc_id": "FAQ-billing-01",
                "snippet": "Go to Settings → Billing → Invoice History. All invoices from "
                           "the past 24 months are available to download as PDF."}],
        "expect_ungrounded": ["automatically emailed", "renewal dates"],
    },
    {
        "id": "T-044",
        "draft": ("I understand you're looking to get a refund. Annual plans are eligible "
                  "for a refund within 14 days of purchase. Please contact our billing team "
                  "to process your refund request."),
        "kb": [{"doc_id": "FAQ-billing-08",
                "snippet": "Refund policy: Annual subscriptions are eligible for a full refund "
                           "if cancelled within 30 days of purchase. Monthly subscriptions are "
                           "not refundable."}],
        "expect_ungrounded": ["14 days"],
    },
    {
        "id": "T-002",
        "draft": ("To reset your password, click 'Forgot Password' on the login page. "
                  "You'll receive a reset email within 2 minutes. If you don't see it, "
                  "check your spam folder."),
        "kb": [{"doc_id": "FAQ-account-01",
                "snippet": "To reset your password: click 'Forgot Password' on the login screen "
                           "and follow the link sent to your registered email."}],
        "expect_ungrounded": ["2 minutes", "spam folder"],
    },
]

for t in TESTS:
    result = compile_grounding(t["draft"], t["kb"])
    print(f"=== {t['id']} ===")
    print(f"  gc_ratio:    {result['grounding_ratio']}")
    print(f"  safe:        {result['auto_reply_safe']}")
    print(f"  claims:      {len(result['claims'])}")
    for c in result['claims']:
        tag = 'UNGND' if not c.get('supported_by_kb') else 'OK   '
        print(f"    [{tag}] {c['text'][:70]}")
    print(f"  ungrounded:  {result['ungrounded_claims']}")
    caught = any(
        any(ex.lower() in u.lower() for u in result['ungrounded_claims'])
        for ex in t['expect_ungrounded']
    )
    print(f"  caught expected ungrounded: {'YES' if caught else 'NO -- MISSED'}")
    print()
