"""Test SSO intent rule — must not break T-031 (invoice wins first)."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    # SSO questions → sso_setup (T-012, T-021)
    ("We need SSO set up with Okta. We are an enterprise customer.", "sso_setup"),
    ("We need to set up SSO with Azure AD. We have 15 users on the Team plan.", "sso_setup"),
    ("Does your product support single sign-on with SAML?", "sso_setup"),
    # T-031: invoice matched first, SSO never fires
    ("Two things: (1) my invoice this month seems higher than expected, and (2) our SSO login has been broken.", "invoice_download"),
    # No regressions
    ("How do I download my invoice?", "invoice_download"),
    ("Can I extend version history beyond 90 days?", "version_history"),
]

all_pass = True
for q, want in CASES:
    r = normalize(q)
    ok = r['intent_id'] == want
    if not ok: all_pass = False
    print(f"  {'OK  ' if ok else 'FAIL'} {q[:72]!r:75s} -> {r['intent_id']}")
print()
print("All pass" if all_pass else "FAILURES DETECTED")
