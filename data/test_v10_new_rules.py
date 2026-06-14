"""Smoke test for v10 new INL rules."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    # T-054: signup_issue → FAQ-troubleshoot-01 → AUTO_REPLY
    ("Where can I report issues with signing up for Acme Collab?", "signup_issue"),
    ("I'm having trouble signing up.", "signup_issue"),
    # T-075: workspace_setup → [] → L1
    ("I need help setting up multiple workspaces on my account.", "workspace_setup"),
    ("How do I create multiple workspaces?", "workspace_setup"),
    # T-010: upload_error → [] → L1
    ("I'm trying to upload a file but I keep getting an error.", "upload_error"),
    ("I keep getting an error when trying to upload a file.", "upload_error"),
    # T-030: ui_preferences → [] → L1
    ("Just wondering if you have dark mode?", "ui_preferences"),
    ("Can I change my notification frequency?", "ui_preferences"),
    # No regressions
    ("How do I reset my password?", "password_reset"),
    ("I want to cancel my subscription.", "cancel_subscription"),
    ("How do I download my invoice?", "invoice_download"),
    ("Set up SSO with Okta.", "sso_setup"),
    ("Can I get a VAT invoice?", "invoice_customize"),
    ("I'm not sure how to cancel my Team plan subscription.", "cancel_subscription"),
    # Signup should not eat unrelated "sign" words
    ("Can I get a single sign-on setup?", "sso_setup"),  # sso_setup has "single sign-on" before signup
]

all_pass = True
for q, want in CASES:
    r = normalize(q)
    ok = r['intent_id'] == want
    if not ok: all_pass = False
    print(f"  {'OK  ' if ok else 'FAIL'} {q[:65]!r:68s} -> {r['intent_id']:25s} (want {want})")
print()
print("All pass" if all_pass else "FAILURES DETECTED")
