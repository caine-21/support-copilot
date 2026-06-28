"""
Churn policy - an explicit, editable semantic layer over churn_signals.

Replaces the implicit policy monopoly (`churn_risk >= 0.8` alone deciding churn)
with a *contestable reading* of WHY each signal counts as churn.

Each churn_signal is read as:
  EXIT_THREAT  - an exit / retention threat (cancel, dispute, leave, competitor, review...)
  TRANSACTION  - a billing / eligibility fact (refund request, usage facts...) - NOT churn alone
  COMMUNICATION_PREFERENCE - newsletter / email notification unsubscribe - NOT product churn

This is NOT a hard classifier - it is an argumentative constraint with teeth:
  all_transaction (no exit reading) -> DEMOTE a high churn_risk to L1 (refund != churn,
                                       and don't auto-reply a refund - a human handles it)
  contested (exit AND transaction)  -> the collapse stands, but it is recorded AND
                                       blocks autonomous AUTO_REPLY (no self-reply under
                                       unresolved disagreement)
  communication preference          -> DEMOTE a high churn_risk to L1; it is not product
                                       churn, but account context ambiguity still blocks
                                       AUTO_REPLY

EXIT_THREAT_MARKERS is the editable policy surface. Edit it; the set of contested /
demoted decisions in the ledger is the worklist that tells you what to edit.

Distribution-shift caveat: this lexicon is deliberately small and WILL miss novel
exit phrasings (false negatives). That is by design - the miss shows up as a routing
divergence in the ledger, which is the pressure to extend the lexicon. The policy is
meant to be wrong-and-visible, not complete.
"""

# -- editable policy surface --
EXIT_THREAT_MARKERS = (
    "threat", "cancel", "dispute", "leave", "leaving", "switch", "competitor",
    "review", "moving on", "move on", "churn", "quit", "terminate", "refund dispute",
)

COMMUNICATION_PREFERENCE_MARKERS = (
    "newsletter", "mailing list", "email notification", "email notifications",
    "marketing email", "marketing emails",
)

COMMUNICATION_ACTION_MARKERS = (
    "unsubscribe", "cancel", "canceling", "cancelling", "subscription",
)


def _is_communication_preference(signal: str, context: str = "") -> bool:
    text = f"{signal} {context}".lower()
    has_channel = any(m in text for m in COMMUNICATION_PREFERENCE_MARKERS)
    has_action = any(m in text for m in COMMUNICATION_ACTION_MARKERS)
    return has_channel and has_action


def _read(signal: str, context: str = "") -> str:
    if _is_communication_preference(signal, context):
        return "COMMUNICATION_PREFERENCE"
    s = signal.lower()
    return "EXIT_THREAT" if any(m in s for m in EXIT_THREAT_MARKERS) else "TRANSACTION"


def resolve_churn(churn_signals: list, context: str = "") -> dict:
    readings = [{"signal": s, "reading": _read(s, context)} for s in (churn_signals or [])]
    kinds = {r["reading"] for r in readings}
    has_exit = "EXIT_THREAT" in kinds
    has_txn  = "TRANSACTION" in kinds
    has_comm = "COMMUNICATION_PREFERENCE" in kinds
    return {
        "readings":        readings,
        "has_exit":        has_exit,
        "all_transaction": has_txn and not has_exit,   # refund-eligibility signature
        "communication_preference": has_comm and not has_exit,
        "non_product_churn": bool(readings) and not has_exit,
        "contested":       has_exit and has_txn,        # both readings present
    }
