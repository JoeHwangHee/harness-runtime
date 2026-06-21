#!/usr/bin/env python3
"""Write rules-pass.json for a plan directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.dont_write_bytecode = True

import harness_hash  # noqa: E402


class RulesPassError(Exception):
    """Expected user-facing rules-pass writer failure."""


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RulesPassError(f"{path} does not exist")
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise RulesPassError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise RulesPassError(f"failed to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RulesPassError(f"{path} must contain a JSON object")
    return payload


def load_findings(path: str | None) -> list[Any]:
    if path is None:
        return []

    findings_path = Path(path)
    try:
        with findings_path.open("r", encoding="utf-8") as f:
            findings = json.load(f)
    except json.JSONDecodeError as exc:
        raise RulesPassError(f"invalid JSON in {findings_path}: {exc}") from exc
    except OSError as exc:
        raise RulesPassError(f"failed to read {findings_path}: {exc}") from exc

    if not isinstance(findings, list):
        raise RulesPassError(f"{findings_path} must contain a JSON array")
    return findings


def required_hash(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise RulesPassError(f"rules.json missing required string field: {field}")
    return value


def write_rules_pass(
    plan_dir: str | Path, verdict: str, findings_file: str | None = None
) -> dict[str, Any]:
    if verdict != "pass":
        raise RulesPassError("only --verdict pass is supported")

    plan_path = Path(plan_dir)
    rules_path = plan_path / "rules.json"
    rules = load_json_object(rules_path)
    findings = load_findings(findings_file)

    marker = {
        "rules_hash": harness_hash.file_hash(rules_path),
        "plan_hash": required_hash(rules, "plan_hash"),
        "brief_hash": required_hash(rules, "brief_hash"),
        "conditions_hash": required_hash(rules, "conditions_hash"),
        "verdict": verdict,
        "findings": findings,
    }

    marker_path = plan_path / "rules-pass.json"
    try:
        marker_path.write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RulesPassError(f"failed to write {marker_path}: {exc}") from exc
    return marker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a rules-pass marker.")
    parser.add_argument("--plan-dir", default=".plan")
    parser.add_argument("--verdict", required=True, choices=["pass"])
    parser.add_argument("--findings-file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        marker = write_rules_pass(args.plan_dir, args.verdict, args.findings_file)
    except RulesPassError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(marker, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
