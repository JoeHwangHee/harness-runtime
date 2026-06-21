#!/usr/bin/env python3
"""Check whether gotchas.md entries are covered by hard compiled rules.

Provides importable pure helpers and a standalone .plan/rules.json gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


sys.dont_write_bytecode = True


GOTCHA_HEADING_RE = re.compile(r"^#{1,6}\s+(G\d+)\b", re.MULTILINE)
GOTCHA_MARKER_RE = re.compile(r"<!--\s*gotcha:\s*(G\d+)\s*-->")
NONE_SENTINEL_RE = re.compile(r"<!--\s*gotchas:\s*none\s*-->", re.IGNORECASE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
GOTCHA_FRAGMENT_RE = re.compile(r"^G\d+$")


def parse_gotcha_ids(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for match in GOTCHA_HEADING_RE.finditer(text):
        matches.append((match.start(), match.group(1)))
    for match in GOTCHA_MARKER_RE.finditer(text):
        matches.append((match.start(), match.group(1)))

    seen: set[str] = set()
    ids: list[str] = []
    for _, gotcha_id in sorted(matches, key=lambda item: item[0]):
        if gotcha_id in seen:
            continue
        seen.add(gotcha_id)
        ids.append(gotcha_id)
    return ids


def has_none_sentinel(text: str) -> bool:
    return bool(NONE_SENTINEL_RE.search(text))


def has_meaningful_content(text: str) -> bool:
    uncommented = HTML_COMMENT_RE.sub("", text)
    for line in uncommented.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return True
    return False


def covered_ids(compiled_rules: list) -> set[str]:
    covered: set[str] = set()

    for rule in compiled_rules:
        if not isinstance(rule, dict):
            continue

        source = str(rule.get("source"))
        if "#" not in source:
            continue

        path_part, fragment = source.split("#", 1)
        basename = path_part.split("/")[-1]
        if basename != "gotchas.md" or not GOTCHA_FRAGMENT_RE.match(fragment):
            continue

        enforce = rule.get("enforce")
        enforce_tokens = set()
        if isinstance(enforce, str):
            enforce_tokens = {part.strip() for part in enforce.split("+")}

        hard = bool(rule.get("requires_test")) or "hook" in enforce_tokens
        if hard:
            covered.add(fragment)

    return covered


def evaluate(gotchas_text: str, compiled_rules: list, waivers: list) -> dict:
    ids = parse_gotcha_ids(gotchas_text)
    sentinel = has_none_sentinel(gotchas_text)
    waived = [
        waiver["gotcha_id"]
        for waiver in waivers
        if isinstance(waiver, dict) and waiver.get("gotcha_id")
    ]

    structural_error = None
    if not ids and not sentinel and has_meaningful_content(gotchas_text):
        structural_error = "gotchas-unstructured"

    covered = covered_ids(compiled_rules)
    waived_set = set(waived)
    uncovered = [
        gotcha_id
        for gotcha_id in ids
        if gotcha_id not in covered and gotcha_id not in waived_set
    ]
    stale_waivers = [gotcha_id for gotcha_id in waived if gotcha_id not in ids]

    return {
        "structural_error": structural_error,
        "uncovered": uncovered,
        "stale_waivers": stale_waivers,
        "ids": ids,
        "covered": sorted(covered),
    }


def load_rules_payload(path: Path):
    if not path.exists():
        print(f"missing required file: {path}", file=sys.stderr)
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {path}: {exc}", file=sys.stderr)
        return None
    except (OSError, UnicodeDecodeError) as exc:
        print(f"failed to read {path}: {exc}", file=sys.stderr)
        return None

    if not isinstance(payload, dict):
        print(f"{path} must contain a JSON object", file=sys.stderr)
        return None
    return payload


def read_gotchas_text(path: Path):
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"failed to read {path}: {exc}", file=sys.stderr)
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", default=".plan")
    args = parser.parse_args(argv)

    plan_dir = Path(args.plan_dir)
    gotchas_text = read_gotchas_text(plan_dir / "gotchas.md")
    if gotchas_text is None:
        return 1

    payload = load_rules_payload(plan_dir / "rules.json")
    if payload is None:
        return 1

    compiled_rules = payload.get("rules", [])
    if not isinstance(compiled_rules, list):
        compiled_rules = []
    waivers = payload.get("waivers", [])
    if not isinstance(waivers, list):
        waivers = []

    result = evaluate(gotchas_text, compiled_rules, waivers)

    for gotcha_id in result["stale_waivers"]:
        print(f"warning: stale waiver: {gotcha_id}", file=sys.stderr)

    if result["structural_error"]:
        print(
            "gotcha gate: "
            f"{result['structural_error']} "
            "(gotchas.md에 ID 없음 — '### Gn:' 형식 또는 '<!-- gotchas: none -->' 명시)",
            file=sys.stderr,
        )
        return 3

    if result["uncovered"]:
        print(f"gotcha gate: uncovered: {','.join(result['uncovered'])}", file=sys.stderr)
        return 3

    print(f"gotcha gate: ok ({len(result['ids'])}개 gotcha, {len(result['covered'])} 커버)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
