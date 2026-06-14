"""Verify sso_setup and signup_issue rule ordering is correct."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from intent_normalizer import normalize

CASES = [
    ("We need to set up SSO with Okta.", "sso_setup"),
    ("Can I get a single sign-on with Azure AD?", "sso_setup"),
    ("Does your platform support SAML?", "sso_setup"),
    ("Where can I sign up for the enterprise plan?", "signup_issue"),
    ("I'm having trouble signing up.", "signup_issue"),
]

all_pass = True
for q, want in CASES:
    r = normalize(q)
    ok = r['intent_id'] == want
    if not ok: all_pass = False
    print(f"  {'OK  ' if ok else 'FAIL'} {q!r} -> {r['intent_id']} (want {want})")
print()
print("All pass" if all_pass else "FAILURES DETECTED")
