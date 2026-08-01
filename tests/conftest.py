import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def manager(selected):
    return lambda _: {"selected_specialists": selected, "detected_domains": selected, "multi_intent": len(selected) > 1, "reason_codes": ["fake"], "confidence": 1.0}


def specialist(name, context):
    return {"applicable": True, "verified_facts": [f"{name} KB fact"], "evidence_doc_ids": ["FAQ-test"], "recommended_route": "no_change", "confidence": 1.0}
