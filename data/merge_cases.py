"""
Merge and validate all test case sources into test_tickets.json.

Sources (in order):
  data/manual_cases.json        T-001 ~ T-035  (hand-designed)
  data/bitext_adapted_v1.json   T-036 ~ T-100  (Bitext + LLM adaptation, frozen)

Run: py data/merge_cases.py  (from support-copilot root)

Adding a new source later:
  1. Generate your file (e.g. bitext_adapted_v2.json)
  2. Add its path to SOURCES below
  3. Re-run — validation will catch any ID conflicts or schema issues
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
from collections import Counter

DATA_DIR = os.path.dirname(__file__)

SOURCES = [
    ("manual",  os.path.join(DATA_DIR, "manual_cases.json")),
    ("bitext_v1", os.path.join(DATA_DIR, "bitext_adapted_v1.json")),
]
OUTPUT = os.path.join(DATA_DIR, "test_tickets.json")
VALID_ACTIONS = {"AUTO_REPLY", "ESCALATE_L1", "ESCALATE_L2"}
REQUIRED_FIELDS = {"id", "user_id", "text", "expected"}


# ── Bootstrap: snapshot manual source if needed ───────────────────────────────

def bootstrap_manual():
    """If manual_cases.json doesn't exist yet, create it from test_tickets.json."""
    manual_path = os.path.join(DATA_DIR, "manual_cases.json")
    if not os.path.exists(manual_path):
        source = os.path.join(DATA_DIR, "test_tickets.json")
        if not os.path.exists(source):
            raise FileNotFoundError("Neither manual_cases.json nor test_tickets.json found.")
        with open(source, encoding="utf-8") as f:
            cases = json.load(f)
        # Keep only cases without bitext source field (manual cases)
        manual = [c for c in cases if not c.get("source") == "bitext"]
        with open(manual_path, "w", encoding="utf-8") as f:
            json.dump(manual, f, ensure_ascii=False, indent=2)
        print(f"[bootstrap] Saved {len(manual)} manual cases → manual_cases.json")
    return manual_path


# ── Validation ────────────────────────────────────────────────────────────────

def validate_required_fields(cases: list[dict], source: str):
    errors = []
    for c in cases:
        missing = REQUIRED_FIELDS - set(c.keys())
        if missing:
            errors.append(f"  {c.get('id', '?')} missing: {missing}")
    if errors:
        raise ValueError(f"[{source}] Required field errors:\n" + "\n".join(errors))


def validate_actions(cases: list[dict], source: str):
    errors = []
    for c in cases:
        action = c.get("expected", {}).get("action")
        if action not in VALID_ACTIONS:
            errors.append(f"  {c['id']}: invalid action '{action}'")
    if errors:
        raise ValueError(f"[{source}] Action errors:\n" + "\n".join(errors))


def validate_unique_ids(all_cases: list[dict]):
    counts = Counter(c["id"] for c in all_cases)
    dupes = [id_ for id_, n in counts.items() if n > 1]
    if dupes:
        raise ValueError(f"Duplicate IDs across sources: {sorted(dupes)}")


def validate_id_sequence(all_cases: list[dict]):
    ids = sorted(c["id"] for c in all_cases)
    expected = [f"T-{i:03d}" for i in range(1, len(all_cases) + 1)]
    if ids != expected:
        missing = sorted(set(expected) - set(ids))
        extra   = sorted(set(ids) - set(expected))
        msg = []
        if missing: msg.append(f"  Missing: {missing}")
        if extra:   msg.append(f"  Extra  : {extra}")
        raise ValueError("ID sequence broken:\n" + "\n".join(msg))


# ── Statistics ────────────────────────────────────────────────────────────────

def routing_reason(case: dict) -> str:
    """Pull routing_reason from expected, then trigger_type, then 'untagged'."""
    rr = case.get("expected", {}).get("routing_reason")
    if rr:
        return rr
    tt = case.get("trigger_type")
    if tt:
        return tt
    return "untagged"


def print_stats(all_cases: list[dict], source_counts: dict[str, int]):
    action_counts = Counter(c["expected"]["action"] for c in all_cases)
    rr_counts     = Counter(routing_reason(c) for c in all_cases)
    ids = sorted(c["id"] for c in all_cases)

    print("\n" + "=" * 55)
    print("MERGE REPORT")
    print("=" * 55)

    for name, count in source_counts.items():
        print(f"  {name + ' cases':<20}: {count}")
    print(f"  {'Total':<20}: {len(all_cases)}")

    print()
    for action, count in sorted(action_counts.items()):
        print(f"  {action:<20}: {count}")

    print()
    print(f"  {'ID coverage':<20}: {ids[0]} ~ {ids[-1]}")

    print()
    print("  Routing reason breakdown:")
    l2_reasons = {"churn_signal","emotional_escalation","contract_risk",
                  "security_concern","hidden_cancel"}
    for reason, count in sorted(rr_counts.items(),
                                 key=lambda x: (x[0] in l2_reasons, x[0])):
        tag = "  [L2]" if reason in l2_reasons else "      "
        print(f"  {tag} {reason:<26}: {count}")

    print()
    print(f"  Validation : PASS")
    print("=" * 55)


# ── Main ──────────────────────────────────────────────────────────────────────

def merge():
    bootstrap_manual()

    all_cases: list[dict] = []
    source_counts: dict[str, int] = {}

    for name, path in SOURCES:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Source not found: {path}\n"
                                    f"Run the corresponding build script first.")
        with open(path, encoding="utf-8") as f:
            cases = json.load(f)

        validate_required_fields(cases, name)
        validate_actions(cases, name)
        source_counts[name] = len(cases)
        all_cases.extend(cases)
        print(f"[load] {name}: {len(cases)} cases from {os.path.basename(path)}")

    validate_unique_ids(all_cases)
    validate_id_sequence(all_cases)

    # Sort by T-ID for deterministic output
    all_cases.sort(key=lambda c: int(c["id"].split("-")[1]))

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_cases, f, ensure_ascii=False, indent=2)

    print_stats(all_cases, source_counts)
    print(f"\n  → {OUTPUT}")


if __name__ == "__main__":
    try:
        merge()
    except (ValueError, FileNotFoundError) as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
