"""
Grounding Compiler (Milestone D).

Enforces KB closure on LLM-generated draft replies:
  draft reply → claim graph → KB support mapping → grounding_ratio

Architecture:
  Layer 1 — retrieval: KB snippets (already done by kb_search step)
  Layer 2 — generation constraint: this module
  Layer 3 — reviewer: ragas_eval faithfulness (post-hoc reporting)

If grounding_ratio < _GROUNDING_REQUIRED (0.75), AUTO_REPLY is blocked.
The reasoner reads obs["grounding_check"] and downgrades action accordingly.

Principle: "LLM must not exceed KB boundary."
Same as routing: move from self-reported grounded=true (noisy)
to claim-by-claim KB verification (deterministic).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from llm import call_llm, safe_json_parse


# Fraction of claims that must be KB-supported for AUTO_REPLY to proceed.
# Below this → action downgraded to ESCALATE_L1.
GROUNDING_REQUIRED: float = 0.75


_CLAIM_GRAPH_SYSTEM = """\
You are a strict grounding verifier for AI-generated customer support replies.

Given a draft reply and KB excerpts, extract all factual claims from the draft,
then classify each as SUPPORTED or UNSUPPORTED by the KB.

UNSUPPORTED — flag as false if ANY of these apply:
  (a) Specific numbers or timeframes not literally in the KB
      e.g. "within 2 minutes", "14-day refund window", "90 days of history"
  (b) Email addresses, URLs, contact details not in the KB
      e.g. "billing@acmecollab.com", "status.acmecollab.com"
  (c) Process steps described in detail the KB does not explicitly describe
      e.g. "invoices are emailed automatically on renewal dates" if KB only says invoices exist
  (d) Product behaviour stated as fact but not literally in the KB
      e.g. "upgrading takes effect immediately and is prorated" if KB does not say this
  (e) Policies inferred but not explicitly stated
      e.g. "monthly plans are not eligible for refunds" if KB only mentions annual plans

SUPPORTED — mark true only if the KB excerpt contains the specific information.
  Paraphrasing is allowed. Reasonable synonyms are allowed.
  Do NOT infer; require explicit or near-explicit presence.

Do NOT extract as claims:
  - Expressions of willingness to help ("I can assist you...")
  - Acknowledgments of the customer's issue
  - Generic closing phrases ("Let me know if you have questions")
  - Offers to escalate or contact support ("please reach out to our team", "contact support for assistance")
  - Meta-statements about KB or documentation coverage ("The KB does not specify...",
    "our documentation doesn't mention...", "I don't have information about...")

Output JSON only:
{
  "claims": [
    {
      "text": "<the specific factual assertion from the draft>",
      "supported_by_kb": true | false,
      "supporting_doc": "<doc_id if supported, null if not>"
    }
  ],
  "grounding_ratio": <0.0–1.0, fraction of claims that are supported>,
  "ungrounded_summary": "<one-sentence description of what facts are not in the KB, or empty string>"
}\
"""


def compile_grounding(draft: str, kb_snippets: list[dict]) -> dict:
    """
    Decompose draft into claims and map each to KB support.

    Returns:
    {
      "claims":           list[{text, supported_by_kb, supporting_doc}],
      "grounding_ratio":  float,    # 1.0 = all claims KB-supported
      "ungrounded_claims": list[str],
      "ungrounded_summary": str,
      "auto_reply_safe":  bool,     # grounding_ratio >= GROUNDING_REQUIRED
    }

    Returns a safe default if draft or kb_snippets are empty (no claims to check).
    """
    if not draft or not kb_snippets:
        return {
            "claims":             [],
            "grounding_ratio":    1.0,
            "ungrounded_claims":  [],
            "ungrounded_summary": "",
            "auto_reply_safe":    True,
        }

    kb_block = "\n\n".join(
        f"[{item['doc_id']}]: {item.get('snippet', '')}" for item in kb_snippets
    )
    user_msg = (
        f"Draft reply:\n{draft}\n\n"
        f"KB excerpts:\n{kb_block}"
    )

    raw    = call_llm(_CLAIM_GRAPH_SYSTEM, user_msg)
    parsed = safe_json_parse(raw)

    claims = parsed.get("claims", [])
    # Recompute ratio from claims list (don't trust LLM's self-reported number)
    if claims:
        supported = sum(1 for c in claims if c.get("supported_by_kb", False))
        ratio = round(supported / len(claims), 3)
    else:
        ratio = 1.0   # no extractable claims → treat as grounded

    ungrounded = [c["text"] for c in claims if not c.get("supported_by_kb", True)]

    return {
        "claims":             claims,
        "grounding_ratio":    ratio,
        "ungrounded_claims":  ungrounded,
        "ungrounded_summary": parsed.get("ungrounded_summary", ""),
        "auto_reply_safe":    ratio >= GROUNDING_REQUIRED,
    }
