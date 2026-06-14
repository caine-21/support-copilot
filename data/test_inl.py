"""Quick smoke test for Intent Normalization Layer."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))

from intent_normalizer import normalize

CASES = [
    # Rule-match cases
    ("Could you help me check what payment methods you support?",       "billing",      False),
    ("Can you tell me what payment methods you actually support?",      "billing",      False),
    ("I need help understanding your refund policy",                    "billing",      False),
    ("In which situations can I request a refund for my subscription?", "billing",      False),
    ("Are there any early termination fees if I cancel my subscription?","billing",     False),
    ("I need help resetting my user password.",                         "account",      False),
    ("I need help switching my workspace to the Team plan.",            "account",      False),
    # Unknown entity detection
    ("I'm not sure how to switch to the Platinum plan.",                "account",      True),
    ("I want to upgrade to the Pro plan.",                              "account",      True),
    # Cancel subscription
    ("I need help canceling my subscription to the workspace plan.",    "cancellation", False),
    ("I need help canceling the company newsletter subscription.",      "cancellation", False),
    # Pass-through (no rule match — LLM fallback, expect non-billing type)
    ("My document won't sync.",                                         "technical",    False),
]

print(f"{'Query':<58} {'intent':<14} {'clarify':<8} {'canonical'}")
print("-" * 110)
for query, exp_intent, exp_clarify in CASES:
    r = normalize(query)
    ok_i = "✓" if r["intent_type"] == exp_intent else f"✗(got {r['intent_type']})"
    ok_c = "✓" if r["requires_clarification"] == exp_clarify else f"✗(got {r['requires_clarification']})"
    print(f"{query[:57]:<58} {ok_i:<14} {ok_c:<8} {r['canonical_query'][:50]}")
