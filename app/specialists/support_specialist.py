"""Support Specialist: intent understanding + grounded draft proposal.

A1 facade is deterministic/offline: the proposal draft is the best KB answer
for this slice, so the proposal is KB-grounded by construction. The specialist
proposes a draft and confidence; it never authorizes any action.
"""
from __future__ import annotations

from .contracts import (
    SpecialistStatus,
    SupportSpecialistInput,
    SupportSpecialistResult,
)


def run_support_specialist(sinput: SupportSpecialistInput) -> SupportSpecialistResult:
    intents = sinput.intents or []
    evidence = sinput.evidence or []

    if not evidence:
        return SupportSpecialistResult(
            request_id=sinput.request_id,
            intents=intents,
            proposal={"draft": "", "grounded": False},
            confidence=0.4,
            reason_codes=["no_evidence"],
            status=SpecialistStatus.NO_EVIDENCE,
        )

    best = evidence[0]
    draft = best.get("snippet", "")
    return SupportSpecialistResult(
        request_id=sinput.request_id,
        intents=intents,
        proposal={"draft": draft, "grounded": True, "doc_id": best.get("doc_id")},
        confidence=0.95,
        reason_codes=["deterministic_kb_draft"],
        evidence_refs=[e.get("doc_id") for e in evidence if e.get("doc_id")],
        status=SpecialistStatus.SUCCESS,
    )
