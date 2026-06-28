"""
Failure Taxonomy — failure is structured, not noisy.

Debug protocol:   map -> class -> layer -> fix     (NOT: log -> patch -> rerun)

A failing case carries a `failure_class` in test_tickets.json. The class names the
RESPONSIBLE LAYER, so a failure routes to a fix-direction by DATA, not by memory.
Extend by adding a class; never overload an existing one.

ONTOLOGY PRE-CHECK (do this FIRST, before layer-classification):
  Confirm the case is the SAME task ontology as the system. If the EXPECTED label
  belongs to a different ontology (e.g. a newsletter unsubscribe expected to escalate
  as product churn), the failure is `ontology_mismatch` — a benchmark/label bug, NOT a
  system failure. Do not touch reader/policy/routing for these. See intent_ontology.py.

How to classify a NEW failure (the criterion):
  - expected belongs to a different task ontology    -> ontology_mismatch  (label / benchmark, pre-system)
  - multiple valid readings of the same signal      -> ambiguity          (reader / representation)
  - real signal missed under STABLE semantics (FN)  -> under_detection    (estimation: text -> signal)
  - a signal over-fires (FP)                         -> over_detection     (reading / semantic policy)
  - decision-gate threshold off                      -> routing_calibration (non-semantic)

Key separation: ambiguity != gap.
  ambiguity -> reader upgrade (representation layer); a lexicon/string match CANNOT fix it.
  gap/miss  -> signal/model upgrade (estimation layer); add coverage.
  gate err  -> routing calibration.
"""

FAILURE_TAXONOMY = {
    "ontology_mismatch": {
        "nature":  "the EXPECTED label conflates two task ontologies",
        "layer":   "ontology (pre-system) — the benchmark label is wrong, not the system",
        "fix":     "correct the case's ontology + expected; do NOT touch reader/policy/routing",
        "example": "T-052 (newsletter unsubscribe = communication_preference, mislabeled as product_churn).",
    },
    "over_detection": {
        "nature":  "false positive — a semantic signal over-fires",
        "layer":   "reading / semantic policy",
        "fix":     "tighten the reading with an explicit, contestable policy",
        "example": "T-018 (refund -> churn). RESOLVED via churn_policy explicit reading.",
    },
    "under_detection": {
        "nature":  "false negative — real signal missed under stable semantics",
        "layer":   "estimation (text -> signal, e.g. tone_check text -> churn_risk)",
        "fix":     "improve signal/model coverage — this is NOT a reading problem",
        "example": "T-052 (real churn scored churn_risk=0.2). OPEN.",
    },
    "ambiguity": {
        "nature":  "multiple valid readings of the same signal",
        "layer":   "representation (the reader itself)",
        "fix":     "context-aware reader upgrade — a lexicon/string match cannot fix this",
        "example": "P2 ('dispute' = chargeback-exit vs invoice-transaction). LATENT reader-upgrade trigger.",
    },
    "routing_calibration": {
        "nature":  "decision-gate threshold off (confidence / grounding)",
        "layer":   "routing (non-semantic)",
        "fix":     "calibrate thresholds — not a semantic-layer issue",
        "example": "T-004 family (AUTO_REPLY -> L1 on confidence/grounding flutter).",
    },
}


def classify_layer(failure_class: str) -> str | None:
    """Map a failure_class to its responsible layer (None for an unknown class)."""
    entry = FAILURE_TAXONOMY.get(failure_class)
    return entry["layer"] if entry else None
