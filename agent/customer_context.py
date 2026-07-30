"""Deterministic Customer Context Beta gate.

Structured customer facts are system inputs. Ticket text may identify which
facts matter, but it never supplies or replaces their values.
"""

from __future__ import annotations

import re


_DOC_REQUIREMENTS = {
    "FAQ-feature-08": ("plan",),
    "FAQ-security-02": ("plan", "region", "contract_status"),
    "FAQ-security-01": ("plan", "role", "permissions"),
    "FAQ-billing-05": ("plan", "role", "permissions", "account_status"),
    "FAQ-feature-02": ("role", "permissions"),
    "FAQ-billing-01": ("account_status", "permissions"),
    "FAQ-billing-04": ("plan", "contract_status"),
    "FAQ-billing-03": ("plan", "contract_status", "account_status"),
    "FAQ-policy-01": ("plan", "contract_status"),
}

_BUSINESS_FIELDS = (
    "plan",
    "region",
    "role",
    "permissions",
    "contract_status",
    "account_status",
)
_ALLOWED_STATUSES = {
    "known",
    "missing",
    "unknown",
    "not_applicable",
    "conflicting",
    "stale",
}
_REQUIRED_PROPERTIES = {
    "value",
    "status",
    "source",
    "updated_at",
    "allowed_for_auto_reply",
}

_STATUS_REASON = {
    "missing": "customer_context_missing",
    "unknown": "customer_context_unknown",
    "not_applicable": "customer_context_not_applicable",
    "conflicting": "customer_context_conflicting",
    "stale": "customer_context_stale",
}

_DOC_AUTHORIZATION = {
    "FAQ-security-01": ({"admin", "owner"}, "configure_security"),
    "FAQ-billing-05": ({"admin", "owner"}, "manage_members"),
    "FAQ-feature-02": ({"admin", "owner"}, "manage_members"),
    "FAQ-billing-01": ({"admin", "owner"}, "manage_billing"),
}

_OVERRIDE_PATTERNS = (
    re.compile(r"\bignore\b.{0,50}\b(profile|record|stored|system)\b", re.IGNORECASE),
    re.compile(r"\bpretend\s+(?:that\s+)?i\s+am\b", re.IGNORECASE),
    re.compile(r"\btreat\s+me\s+as\b", re.IGNORECASE),
)


def _validate_context(customer_context: dict) -> dict:
    fields = customer_context.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("customer_context.fields must be an object")
    for field_name in _BUSINESS_FIELDS:
        field = fields.get(field_name)
        if not isinstance(field, dict):
            raise ValueError(f"{field_name} must be present as an object")
        missing = sorted(_REQUIRED_PROPERTIES - set(field))
        if missing:
            raise ValueError(f"{field_name} missing properties: {', '.join(missing)}")
        if field["status"] not in _ALLOWED_STATUSES:
            raise ValueError(f"{field_name} has invalid status: {field['status']}")
    return fields


def evaluate_customer_context(
    ticket_text: str,
    kb_results: list[dict],
    customer_context: dict,
) -> dict:
    """Return the customer facts that may participate in auto-reply authorization."""
    doc_ids = {row.get("doc_id") for row in kb_results}
    relevant_fields: list[str] = []
    for doc_id, fields in _DOC_REQUIREMENTS.items():
        if doc_id in doc_ids:
            relevant_fields.extend(field for field in fields if field not in relevant_fields)

    context_fields = _validate_context(customer_context)
    used_fields = [field for field in relevant_fields if field in context_fields]
    blocking_fields: list[str] = []
    reason_codes: list[str] = []
    if any(pattern.search(ticket_text) for pattern in _OVERRIDE_PATTERNS):
        reason_codes.append("ticket_context_override_attempt")
    for field_name in relevant_fields:
        field = context_fields.get(field_name, {})
        status = field.get("status", "missing")
        reason_code = _STATUS_REASON.get(status)
        if reason_code:
            blocking_fields.append(field_name)
            if reason_code not in reason_codes:
                reason_codes.append(reason_code)
        elif not field.get("allowed_for_auto_reply", False):
            blocking_fields.append(field_name)
            if "customer_context_not_authorized" not in reason_codes:
                reason_codes.append("customer_context_not_authorized")

    plan = context_fields.get("plan", {}).get("value")
    region = context_fields.get("region", {}).get("value")
    plan_is_usable = context_fields.get("plan", {}).get("status") == "known"
    region_is_usable = context_fields.get("region", {}).get("status") == "known"
    plan_mismatch = (
        ("FAQ-billing-04" in doc_ids and plan_is_usable and plan != "enterprise")
        or (
            "FAQ-security-02" in doc_ids
            and region_is_usable
            and region == "EU"
            and plan_is_usable
            and plan != "enterprise"
        )
    )
    if plan_mismatch:
        if "plan" not in blocking_fields:
            blocking_fields.append("plan")
        if "customer_context_plan_mismatch" not in reason_codes:
            reason_codes.append("customer_context_plan_mismatch")

    for doc_id, (allowed_roles, required_permission) in _DOC_AUTHORIZATION.items():
        if doc_id not in doc_ids:
            continue
        role_field = context_fields.get("role", {})
        permission_field = context_fields.get("permissions", {})
        role_usable = (
            role_field.get("status") == "known"
            and role_field.get("allowed_for_auto_reply") is True
        )
        permission_usable = (
            permission_field.get("status") == "known"
            and permission_field.get("allowed_for_auto_reply") is True
        )
        if not (role_usable and permission_usable):
            continue
        denied_fields = []
        if role_field.get("value") not in allowed_roles:
            denied_fields.append("role")
        if required_permission not in (permission_field.get("value") or []):
            denied_fields.append("permissions")
        if denied_fields:
            for field_name in denied_fields:
                if field_name not in blocking_fields:
                    blocking_fields.append(field_name)
            if "customer_context_permission_denied" not in reason_codes:
                reason_codes.append("customer_context_permission_denied")

    safe = not blocking_fields and not reason_codes
    return {
        "safe_for_auto_reply": safe,
        "relevant_fields": relevant_fields,
        "used_fields": used_fields,
        "blocking_fields": blocking_fields,
        "reason_codes": reason_codes or ["customer_context_ok"],
        "field_states": {
            field_name: dict(context_fields[field_name])
            for field_name in relevant_fields
        },
    }
