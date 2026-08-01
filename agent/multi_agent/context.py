"""Domain-minimised contexts. Specialists never receive the raw ticket."""
from __future__ import annotations
import re
KB_DOMAIN_BY_DOC_ID = {"FAQ-billing-01":"billing", "FAQ-billing-03":"billing", "FAQ-billing-04":"billing", "FAQ-billing-05":"billing", "FAQ-billing-06":"billing", "FAQ-billing-07":"billing", "FAQ-billing-08":"billing", "FAQ-account-01":"technical", "FAQ-account-02":"technical", "FAQ-troubleshoot-01":"technical", "FAQ-troubleshoot-06":"technical", "FAQ-security-01":"technical", "FAQ-security-02":"technical", "FAQ-security-03":"technical", "FAQ-feature-02":"technical", "FAQ-feature-04":"shared", "FAQ-feature-07":"shared", "FAQ-policy-01":"shared"}
_HINTS = {"billing": ("invoice", "payment", "refund", "charged", "subscription", "price", "contract", "seat"), "technical": ("bug", "error", "login", "access", "sync", "configuration", "incident", "sso")}
def _relevant_kb(rows, domain):
    return [{key: row.get(key) for key in ("doc_id", "score", "snippet", "method") if key in row} for row in rows if KB_DOMAIN_BY_DOC_ID.get(row.get("doc_id")) in (domain, "shared")]
def _normalized(value):
    return re.sub(r"\s+", " ", value).strip()

def fallback_slices(ticket, selected):
    source = _normalized(ticket)
    clauses = [_normalized(part) for part in re.split(r"(?<=[.!?])\s+|\s+(?:and|but)\s+", ticket) if part.strip()]
    slices = []
    for name in selected:
        excerpts = list(dict.fromkeys(clause for clause in clauses if any(word in clause.lower() for word in _HINTS[name])))[:4]
        if not excerpts and len(selected) == 1 and source:
            excerpts = [source]
        slices.append({"specialist": name, "excerpts": excerpts, "reason_codes": ["domain_slice_fallback_used"]})
    return slices
def validate_slices(ticket, selected, slices):
    source = _normalized(ticket); accepted=[]; errors=[]; seen=set()
    for row in slices:
        if row.specialist not in selected:
            errors.append("manager_slice_unselected")
            continue
        excerpts=[excerpt for excerpt in row.excerpts if _normalized(excerpt) in source]
        if len(excerpts) != len(row.excerpts): errors.append("manager_excerpt_invalid")
        if not excerpts:
            errors.append("manager_slice_missing")
            continue
        seen.add(row.specialist)
        accepted.append({"specialist":row.specialist,"excerpts":list(dict.fromkeys(excerpts)),"reason_codes":row.reason_codes})
    if seen != set(selected): errors.append("manager_slice_missing")
    if len(selected) > 1 and len(accepted) == len(selected):
        excerpt_sets = {row["specialist"]: frozenset(_normalized(item) for item in row["excerpts"]) for row in accepted}
        if len(set(excerpt_sets.values())) != len(excerpt_sets): errors.append("domain_slice_not_isolated")
        if all(excerpt_sets[name] == {source} for name in selected): errors.append("domain_slice_full_ticket_shared")
    if errors: return [], list(dict.fromkeys(errors))
    return accepted, []
def _field(context, name):
    field = (context or {}).get("fields", {}).get(name, {})
    return {key: field.get(key) for key in ("value", "status")}
def build_manager_context(ticket_text, classification, tone, kb_results, **_):
    return {"ticket_text": ticket_text, "classification": {k: classification.get(k) for k in ("intent", "secondary_intent", "confidence")}, "intent_set": classification.get("intent_set", []), "tone_summary": {k: tone.get(k) for k in ("tone", "churn_risk", "urgency")}, "kb": [{k: row.get(k) for k in ("doc_id", "score", "method")} for row in kb_results]}
def build_billing_context(ticket_id=None, classification=None, kb_results=None, customer_context=None, domain_slice=None, tone=None, **_):
    return {"ticket_id":ticket_id,"billing_ticket_excerpts":(domain_slice or {}).get("excerpts",[]),"classification":{k:(classification or {}).get(k) for k in ("intent","secondary_intent","confidence")},"shared_risk_summary":{k:(tone or {}).get(k) for k in ("tone","urgency")},"kb":_relevant_kb(kb_results or [],"billing"),"plan":_field(customer_context,"plan"),"contract_status":_field(customer_context,"contract_status"),"account_status":_field(customer_context,"account_status"),"role":_field(customer_context,"role"),"permissions":_field(customer_context,"permissions")}
def build_technical_context(ticket_id=None, classification=None, kb_results=None, history=None, domain_slice=None, tone=None, **_):
    return {"ticket_id":ticket_id,"technical_ticket_excerpts":(domain_slice or {}).get("excerpts",[]),"classification":{k:(classification or {}).get(k) for k in ("intent","secondary_intent","confidence")},"shared_risk_summary":{k:(tone or {}).get(k) for k in ("tone","urgency")},"kb":_relevant_kb(kb_results or [],"technical"),"technical_history_summary":[{k:ticket.get(k) for k in ("ticket_id","intent","action")} for ticket in (history or {}).get("past_tickets",[]) if ticket.get("intent") in ("bug","account")],"environment":None}
