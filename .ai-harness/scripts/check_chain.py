#!/usr/bin/env python3
"""Check the plan review hash chain before go-time work starts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.dont_write_bytecode = True

import harness_hash  # noqa: E402


CONDITIONS_MARKER_RE = re.compile(r"^<!--\s*conditions_hash:\s*(\S+)\s*-->$")


class ChainBroken(Exception):
    """Expected user-facing chain check failure."""

    def __init__(self, link: str, detail: str) -> None:
        super().__init__(detail)
        self.link = link
        self.detail = detail


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise ChainBroken("input", f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ChainBroken("input", f"failed to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ChainBroken("input", f"{path} must contain a JSON object")
    return payload


def require_inputs(plan_dir: Path) -> None:
    required = [
        plan_dir / "plan.md",
        plan_dir / "review-brief.md",
        plan_dir / "review-pass.json",
        plan_dir / "rules.json",
        plan_dir / "rules-pass.json",
    ]
    required.extend(plan_dir / name for name in harness_hash.CONDITION_FILES)

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        noun = "file" if len(missing) == 1 else "files"
        raise ChainBroken("input", f"missing required {noun}: {', '.join(missing)}")


def extract_brief_conditions_hash(brief_path: Path) -> str | None:
    first_line = brief_path.read_text(encoding="utf-8").splitlines()[0:1]
    if not first_line:
        return None
    match = CONDITIONS_MARKER_RE.match(first_line[0])
    if not match:
        return None
    return match.group(1)


def mismatch(actual: Any, expected: str) -> bool:
    return not isinstance(actual, str) or actual != expected


def fail_if_hash_mismatch(
    link: str,
    payload: dict[str, Any],
    label: str,
    field: str,
    expected: str,
) -> None:
    actual = payload.get(field)
    if mismatch(actual, expected):
        raise ChainBroken(
            link,
            f"{label}.{field} {actual!r} != expected {expected}",
        )


def check_chain(plan_dir: str | Path) -> None:
    plan_path = Path(plan_dir)
    plan_file = plan_path / "plan.md"
    brief_file = plan_path / "review-brief.md"
    review_pass_file = plan_path / "review-pass.json"
    rules_file = plan_path / "rules.json"
    rules_pass_file = plan_path / "rules-pass.json"

    require_inputs(plan_path)

    try:
        plan_hash = harness_hash.file_hash(plan_file)
        brief_hash = harness_hash.file_hash(brief_file)
        current_conditions_hash = harness_hash.conditions_hash(plan_path)
        rules_hash = harness_hash.file_hash(rules_file)
        brief_conditions_hash = extract_brief_conditions_hash(brief_file)
    except (OSError, UnicodeDecodeError) as exc:
        raise ChainBroken("input", f"failed to read required input: {exc}") from exc

    if brief_conditions_hash != current_conditions_hash:
        raise ChainBroken(
            "L1",
            "review-brief conditions_hash "
            f"{brief_conditions_hash!r} != current conditions_hash "
            f"{current_conditions_hash}",
        )

    review_pass = load_json_object(review_pass_file)
    fail_if_hash_mismatch("L2", review_pass, "review-pass", "plan_hash", plan_hash)
    fail_if_hash_mismatch("L2", review_pass, "review-pass", "brief_hash", brief_hash)

    rules = load_json_object(rules_file)
    fail_if_hash_mismatch("L3", rules, "rules", "plan_hash", plan_hash)
    fail_if_hash_mismatch("L3", rules, "rules", "brief_hash", brief_hash)
    fail_if_hash_mismatch(
        "L3", rules, "rules", "conditions_hash", current_conditions_hash
    )

    rules_pass = load_json_object(rules_pass_file)
    fail_if_hash_mismatch("L4", rules_pass, "rules-pass", "rules_hash", rules_hash)
    for field in ("plan_hash", "brief_hash", "conditions_hash"):
        expected = rules.get(field)
        actual = rules_pass.get(field)
        if not isinstance(expected, str):
            raise ChainBroken("L4", f"rules.{field} {expected!r} is not a string")
        if mismatch(actual, expected):
            raise ChainBroken(
                "L4",
                f"rules-pass.{field} {actual!r} != rules.{field} {expected}",
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a plan artifact hash chain.")
    parser.add_argument("--plan-dir", default=".plan")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        check_chain(args.plan_dir)
    except ChainBroken as exc:
        print(f"chain broken at {exc.link}: {exc.detail}", file=sys.stderr)
        return 4

    print("chain ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
