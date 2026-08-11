"""Fail fast on common text-encoding regressions in repository text files."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = (
    "CANONICAL_FACTS.md",
    "README.md",
    "PRODUCTION_GAP.md",
    "docs/AGENT_TOOLING.md",
    "docs/OPERATIONS.md",
    "docs/RUNBOOK.md",
    "docs/SECURITY_REVIEW.md",
)
TEXT_SUFFIXES = {".md", ".json", ".yml", ".yaml", ".py", ".js"}
MOJIBAKE_MARKERS = re.compile(r"(?:鈥|鈫|锟|馃|ï¿½|Ã.|Â.|â.)")
QUESTION_RUN = re.compile(r"\?{3,}")
STANDALONE_QUESTION = re.compile(r"(?<!\S)\?(?!\S)")


def tracked_text_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    paths: list[Path] = []
    for value in result.stdout.splitlines():
        path = Path(value)
        if path.name == "Dockerfile" or path.suffix.lower() in TEXT_SUFFIXES:
            paths.append(path)
    return paths


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan(path: Path) -> list[str]:
    if path.as_posix() == "scripts/check_text_integrity.py":
        return []
    full_path = ROOT / path
    try:
        raw = full_path.read_bytes()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    issues: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        issues.append(f"{path}:1: UTF-8 BOM is not allowed")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{path}:1: invalid UTF-8: {exc}"]

    checks = [
        ("U+FFFD replacement character", re.compile("\ufffd")),
        ("suspicious question-mark run", QUESTION_RUN),
        ("common mojibake marker", MOJIBAKE_MARKERS),
    ]
    # A standalone '?' is suspicious in prose (e.g. an arrow replaced by '?')
    # but is valid in source SQL placeholders and ordinary code.
    if path.suffix.lower() in {".md", ".json", ".yml", ".yaml"}:
        checks.insert(2, ("standalone question-mark replacement", STANDALONE_QUESTION))
    for label, pattern in checks:
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 28)
            end = min(len(text), match.end() + 28)
            snippet = text[start:end].replace("\n", " ")
            issues.append(f"{path}:{line_number(text, match.start())}: {label}: {snippet!r}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="text files to scan")
    parser.add_argument("--all-text", action="store_true", help="scan all tracked text files")
    args = parser.parse_args()

    if args.all_text and args.paths:
        parser.error("use --all-text or explicit paths, not both")
    selected = tracked_text_paths() if args.all_text else [Path(value) for value in (args.paths or DEFAULT_PATHS)]
    issues = [issue for path in selected for issue in scan(path)]
    if issues:
        print("TEXT INTEGRITY: FAIL")
        print("\n".join(issues))
        return 1
    print(f"TEXT INTEGRITY: PASS ({len(selected)} files, UTF-8, no suspicious markers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
