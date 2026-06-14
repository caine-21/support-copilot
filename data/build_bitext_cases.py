"""
Build 65 new test cases (T-036 to T-100) via Bitext domain adaptation.

Pipeline:
  Bitext raw text
    → Phase 1: SaaS rewrite   (all classes)
    → Phase 2: Risk injection  (L2 only)

Output distribution:
  T-036 to T-054 : 19 AUTO_REPLY   (SaaS rewrite only)
  T-055 to T-075 : 21 ESCALATE_L1  (SaaS rewrite only)
  T-076 to T-100 : 25 ESCALATE_L2  (SaaS rewrite + risk injection)

Run: py data/build_bitext_cases.py  (from support-copilot root)
"""
import sys, os, json, random, time, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

from datasets import load_dataset
from agent.llm import call_llm

# ── Sampling plan ─────────────────────────────────────────────────────────────

AUTO_PLAN = {
    "check_invoice":           ("kb_answerable",  2),
    "get_invoice":             ("kb_answerable",  2),
    "check_payment_methods":   ("policy_inquiry", 2),
    "check_refund_policy":     ("policy_inquiry", 2),
    "check_cancellation_fee":  ("policy_inquiry", 2),
    "recover_password":        ("how_to_request", 1),
    "edit_account":            ("how_to_request", 2),
    "create_account":          ("how_to_request", 1),
    "switch_account":          ("how_to_request", 2),
    "newsletter_subscription": ("settings_change",2),
    "registration_problems":   ("how_to_request", 1),
}

L1_PLAN = {
    "payment_issue":       ("payment_issue",   3),
    "contact_human_agent": ("human_requested", 3),
    "track_refund":        ("status_inquiry",  3),
    "track_order":         ("status_inquiry",  2),
    "delivery_period":     ("status_inquiry",  2),
    "change_order":        ("account_change",  2),
    "delete_account":      ("account_change",  2),
    "review":              ("feedback",        2),
    "place_order":         ("account_change",  2),
}

# L2: 25 cases = 5 trigger_types × 5 each
# Source pool: cancel_order(9) + get_refund(8) + complaint(8)
L2_SOURCES = ["cancel_order"] * 9 + ["get_refund"] * 8 + ["complaint"] * 8
L2_TRIGGER_TYPES = (
    ["churn_signal"] * 5 +
    ["emotional_escalation"] * 5 +
    ["contract_risk"] * 5 +
    ["security_concern"] * 5 +
    ["hidden_cancel"] * 5
)

# ── Prompts ───────────────────────────────────────────────────────────────────

REWRITE_SYSTEM = """You adapt customer support messages from e-commerce to B2B SaaS context (Acme Collab — a workspace and document collaboration platform).

Rewrite naturally for a SaaS user. Preserve:
- The user's underlying intent
- The emotional tone and frustration level
- The complexity of the situation

Replace e-commerce concepts with SaaS equivalents:
- order / item / product → subscription / workspace / document / feature / plan
- shipping / delivery → access / export / onboarding / feature
- store / shop → platform / dashboard / app
- purchase → subscription / plan renewal
- cancel order → cancel subscription
- track order → check ticket status / follow up on support request
- place order → set up account / activate plan
- return / refund for product → refund for plan / subscription credit

Output ONLY the rewritten message. No explanation, no quotes."""

INJECT_SYSTEM = """You inject a specific risk signal into a customer support message to escalate it to high-priority (L2) routing.

Risk types and what to inject:
- churn_signal: add explicit cancellation intent, competitor evaluation, or major account downsizing
- emotional_escalation: add threats to post publicly, invoke senior executive, or reference repeated failed attempts
- contract_risk: add SLA breach claim, legal team involvement, compliance audit, or formal documentation demand
- security_concern: add SOC 2 audit request, compliance review, security team involvement, data exposure or breach concern, or access control/permission audit
- hidden_cancel: embed a clear exit signal (export all data, transfer ownership, justify renewal cost) as a secondary request within a legitimate question

Rules:
- Keep the original request — add the risk signal on top, don't replace it
- The addition must feel natural and specific (add a detail, not a generic complaint)
- Result should be 1–3 sentences total
- Output ONLY the final message. No explanation."""


def rewrite(text: str, intent: str) -> str:
    text = clean_placeholders(text)
    try:
        result = call_llm(REWRITE_SYSTEM, f"Intent: {intent}\nMessage: {text}",
                          json_mode=False)
        return clean_placeholders(result.strip().strip('"'))
    except Exception as e:
        print(f"  [warn] rewrite failed ({intent}): {e}")
        return text


def inject_risk(text: str, trigger_type: str) -> str:
    try:
        result = call_llm(INJECT_SYSTEM,
                          f"Risk type: {trigger_type}\nMessage: {text}",
                          json_mode=False)
        return result.strip().strip('"')
    except Exception as e:
        print(f"  [warn] inject failed ({trigger_type}): {e}")
        return text


_PLACEHOLDER_MAP = [
    (r"\{\{Order Number\}\}",          "SUB-28471"),
    (r"\{\{Currency Symbol\}\}\{\{Refund Amount\}\}", "$149"),
    (r"\{\{Refund Amount\}\}",         "149"),
    (r"\{\{Currency Symbol\}\}",       "$"),
    (r"\{\{Person Name\}\}",           "the account owner"),
    (r"\{\{Account Type\}\}",          "Professional"),
    (r"\{\{Account Category\}\}",      "Team plan"),
    (r"\{\{Account Card Type\}\}",     "credit card"),
    (r"\{\{Date\}\}",                  "last Tuesday"),
    (r"\{\{[^}]+\}\}",                 "the account"),   # catch-all
]

def clean_placeholders(text: str) -> str:
    for pattern, replacement in _PLACEHOLDER_MAP:
        text = re.sub(pattern, replacement, text)
    return text


def sample_pool(ds_by_intent: dict, intent: str, n: int, seed: int) -> list[str]:
    pool = ds_by_intent.get(intent, [])
    random.seed(seed)
    return random.sample(pool, min(n, len(pool)))


def build_cases():
    print("Loading Bitext dataset...")
    ds = load_dataset("bitext/Bitext-customer-support-llm-chatbot-training-dataset",
                      split="train")
    ds_by_intent: dict[str, list[str]] = {}
    for row in ds:
        ds_by_intent.setdefault(row["intent"], []).append(row["instruction"])

    cases = []
    ticket_id = 36

    # ── Phase 1a: AUTO_REPLY ──────────────────────────────────────────────────
    print(f"\nBuilding AUTO_REPLY cases (T-{ticket_id:03d}+)...")
    for intent, (routing_reason, n) in AUTO_PLAN.items():
        samples = sample_pool(ds_by_intent, intent, n, seed=ticket_id)
        for raw in samples:
            adapted = rewrite(raw, intent)
            tid = f"T-{ticket_id:03d}"
            cases.append({
                "id":       tid,
                "user_id":  f"U-{600 + ticket_id}",
                "text":     adapted,
                "original_text":    raw,
                "difficulty": "easy",
                "source":           "bitext",
                "original_intent":  intent,
                "adapted_domain":   "saas",
                "generation_method":"llm_rewrite",
                "expected": {
                    "action":         "AUTO_REPLY",
                    "min_confidence": 0.7,
                    "routing_reason": routing_reason,
                },
            })
            print(f"  [{tid}] AUTO  {routing_reason:16s}  {adapted[:55]}...")
            ticket_id += 1
            time.sleep(0.3)

    # ── Phase 1b: ESCALATE_L1 ─────────────────────────────────────────────────
    print(f"\nBuilding ESCALATE_L1 cases (T-{ticket_id:03d}+)...")
    for intent, (routing_reason, n) in L1_PLAN.items():
        samples = sample_pool(ds_by_intent, intent, n, seed=ticket_id)
        for raw in samples:
            adapted = rewrite(raw, intent)
            tid = f"T-{ticket_id:03d}"
            cases.append({
                "id":       tid,
                "user_id":  f"U-{600 + ticket_id}",
                "text":     adapted,
                "original_text":    raw,
                "difficulty": "medium",
                "source":           "bitext",
                "original_intent":  intent,
                "adapted_domain":   "saas",
                "generation_method":"llm_rewrite",
                "expected": {
                    "action":         "ESCALATE_L1",
                    "routing_reason": routing_reason,
                },
            })
            print(f"  [{tid}] L1    {routing_reason:16s}  {adapted[:55]}...")
            ticket_id += 1
            time.sleep(0.3)

    # ── Phase 2: ESCALATE_L2 (rewrite + risk injection) ──────────────────────
    print(f"\nBuilding ESCALATE_L2 cases (T-{ticket_id:03d}+)...")
    random.seed(99)
    shuffled_sources = L2_SOURCES[:]
    random.shuffle(shuffled_sources)

    for i, (source_intent, trigger_type) in enumerate(
            zip(shuffled_sources, L2_TRIGGER_TYPES)):
        raw_pool = ds_by_intent.get(source_intent, [])
        raw = random.choice(raw_pool)

        adapted   = rewrite(raw, source_intent)
        time.sleep(0.3)
        injected  = inject_risk(adapted, trigger_type)
        time.sleep(0.3)

        tid = f"T-{ticket_id:03d}"
        cases.append({
            "id":       tid,
            "user_id":  f"U-{600 + ticket_id}",
            "text":     injected,
            "original_text":    raw,
            "difficulty": "hard",
            "source":           "bitext",
            "original_intent":  source_intent,
            "adapted_domain":   "saas",
            "generation_method":"llm_rewrite+risk_injection",
            "trigger_type":     trigger_type,
            "expected": {
                "action":         "ESCALATE_L2",
                "routing_reason": trigger_type,
                # hidden_cancel is detected by keyword gate, not LLM tone model —
                # churn_risk will be low by design, so no min constraint here
                **({} if trigger_type == "hidden_cancel" else {"churn_risk_min": 0.55}),
            },
        })
        print(f"  [{tid}] L2    {trigger_type:22s}  {injected[:50]}...")
        ticket_id += 1

    # ── Save ──────────────────────────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(__file__), "bitext_adapted_v1.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)

    by_class = {"AUTO_REPLY": 0, "ESCALATE_L1": 0, "ESCALATE_L2": 0}
    for c in cases:
        by_class[c["expected"]["action"]] += 1

    print(f"\n{'='*60}")
    print(f"Done. {len(cases)} cases → {out_path}")
    print(f"  AUTO_REPLY   : {by_class['AUTO_REPLY']}")
    print(f"  ESCALATE_L1  : {by_class['ESCALATE_L1']}")
    print(f"  ESCALATE_L2  : {by_class['ESCALATE_L2']}")
    print(f"  T-range      : T-036 to T-{ticket_id - 1:03d}")
    print(f"\nDataset frozen at v1. Do NOT re-run to regenerate — edit test_tickets.json directly.")
    print(f"Next step: py data/merge_cases.py")


if __name__ == "__main__":
    build_cases()
