"""
Intent Ontology — what KIND of task a ticket is, BEFORE asking how it routes.

The failure taxonomy classifies failures WITHIN a task. But some "failures" are
cross-task conflations: the expected label belongs to a different task ontology.
The ontology is the PRE-FILTER that catches this before layer-classification.

The domain rule that was missing: only `product_churn` is churn-eligible. A
communication_preference ticket ("unsubscribe from the newsletter") is NOT product
churn — scoring it as churn, or expecting an L2 churn escalation, is an
`ontology_mismatch` (a benchmark/label bug), not under_detection of the system.

Extend by adding an ontology; never overload churn semantics across ontologies.
"""

INTENT_ONTOLOGY = {
    "product_churn": {
        "meaning":        "intent to stop using / cancel the PRODUCT or downgrade revenue",
        "churn_eligible": True,
        "example":        "I'm cancelling and moving to a competitor.",
    },
    "support_intent": {
        "meaning":        "a how-to / bug / account / billing support request",
        "churn_eligible": False,
        "example":        "How do I reset my password?",
    },
    "communication_preference": {
        "meaning":        "manage notifications / newsletters / contact preferences",
        "churn_eligible": False,
        "example":        "Unsubscribe me from the company newsletter.",
    },
}


def is_churn_eligible(ontology: str) -> bool:
    """True only for ontologies where churn is a meaningful signal (product_churn)."""
    entry = INTENT_ONTOLOGY.get(ontology)
    return bool(entry and entry["churn_eligible"])
