"""Sanitize an incident/failure into a review-gated eval candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*")
_SECRET = re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+")


def sanitize(value):
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items() if str(key).lower() not in {"authorization", "raw_payload"}}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        value = _EMAIL.sub("<redacted-email>", value)
        value = _BEARER.sub("Bearer <redacted>", value)
        return _SECRET.sub(lambda match: f"{match.group(1)}=<redacted>", value)[:4_000]
    return value


def build_candidate(source: dict) -> dict:
    cleaned = sanitize(source)
    digest = hashlib.sha256(json.dumps(cleaned, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    return {
        "candidate_id": f"REG-{digest}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "review_status": "pending_human_review",
        "promotion_policy": "never enters regression suite until reviewer approves expected behavior",
        "source": cleaned,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/regression_candidates"))
    args = parser.parse_args()
    candidate = build_candidate(json.loads(args.source.read_text(encoding="utf-8")))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"{candidate['candidate_id']}.json"
    output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
