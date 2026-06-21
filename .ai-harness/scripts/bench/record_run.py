#!/usr/bin/env python3
"""Passively record go-run telemetry derived from harness contracts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional


COST_NOTE = "harness-level (MAIN-held), not script-captured"


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_ts(ts: datetime) -> str:
    return ts.isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json_object(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        warn(f"could not read {path}: {exc}")
        return {}

    if not isinstance(payload, dict):
        warn(f"{path} does not contain a JSON object")
        return {}
    return payload


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def parse_started_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None

    candidate = value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def duration_seconds(active_run: dict[str, Any], now: datetime) -> Optional[int]:
    started = parse_started_ts(active_run.get("started_ts"))
    if started is None:
        return None
    return int((now - started).total_seconds())


def enforce_contains_hook(enforce: Any) -> bool:
    if not isinstance(enforce, str):
        return False
    return "hook" in {part.strip() for part in enforce.split("+")}


def rules_metrics(rules_payload: dict[str, Any]) -> dict[str, Any]:
    rules = as_list(rules_payload.get("rules"))
    by_enforce: dict[str, int] = {}

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        enforce = rule.get("enforce")
        if isinstance(enforce, str):
            by_enforce[enforce] = by_enforce.get(enforce, 0) + 1

    scope = rules_payload.get("scope")
    allow_globs = as_list(scope.get("allow_globs")) if isinstance(scope, dict) else []
    verification = rules_payload.get("verification")
    commands = as_list(verification.get("commands")) if isinstance(verification, dict) else []

    return {
        "total": len(rules),
        "by_enforce": by_enforce,
        "scope_globs": len(allow_globs),
        "verification_commands": len(commands),
    }


def ledger_metrics(ledger_payload: dict[str, Any]) -> dict[str, int]:
    entries = as_list(ledger_payload.get("required_tests"))
    satisfied = 0
    for entry in entries:
        if isinstance(entry, dict) and entry.get("status") == "satisfied":
            satisfied += 1

    required = len(entries)
    return {
        "required": required,
        "satisfied": satisfied,
        "declared_remaining": max(required - satisfied, 0),
    }


def gate_metrics(final_review_payload: dict[str, Any]) -> dict[str, Optional[str]]:
    verdict = final_review_payload.get("verdict")
    final_diff_verdict = final_review_payload.get("final_diff_verdict")
    return {
        "reviewer_verdict": verdict if isinstance(verdict, str) else None,
        "final_diff_verdict": final_diff_verdict
        if isinstance(final_diff_verdict, str)
        else None,
    }


def ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def effect_axes(
    rules_payload: dict[str, Any], final_review_payload: dict[str, Any]
) -> dict[str, Optional[float]]:
    rules = as_list(rules_payload.get("rules"))

    provenance_count = 0
    hook_count = 0
    unfireable_count = 0

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("source") and rule.get("plan_step"):
            provenance_count += 1

        if enforce_contains_hook(rule.get("enforce")):
            hook_count += 1
            if not rule.get("detect") and not rule.get("path_glob"):
                unfireable_count += 1

    reviewer_checks = as_list(final_review_payload.get("reviewer_checks"))
    reviewer_passes = 0
    for check in reviewer_checks:
        if isinstance(check, dict) and check.get("verdict") == "pass":
            reviewer_passes += 1

    return {
        "provenance_rate": ratio(provenance_count, len(rules)),
        "unfireable_block_rate": ratio(unfireable_count, hook_count),
        "reviewer_pass_rate": ratio(reviewer_passes, len(reviewer_checks)),
    }


def build_record(plan_dir: str, run_id: str, now: datetime) -> dict[str, Any]:
    rules_payload = load_json_object(os.path.join(plan_dir, "rules.json"))
    active_run = load_json_object(os.path.join(plan_dir, "active-run.json"))
    ledger_payload = load_json_object(os.path.join(plan_dir, "test-ledger.json"))
    final_review_payload = load_json_object(
        os.path.join(plan_dir, "final-review-pass.json")
    )

    return {
        "run_id": run_id,
        "recorded_ts": format_ts(now),
        "duration_s": duration_seconds(active_run, now),
        "rules": rules_metrics(rules_payload),
        "ledger": ledger_metrics(ledger_payload),
        "gate": gate_metrics(final_review_payload),
        "effect_axes": effect_axes(rules_payload, final_review_payload),
        "cost": {"tokens": None, "turns": None, "note": COST_NOTE},
        "self_modify": False,
    }


def write_record(plan_dir: str, run_id: str, record: dict[str, Any]) -> None:
    runs_dir = os.path.join(plan_dir, "bench", "runs")
    os.makedirs(runs_dir, exist_ok=True)
    output_path = os.path.join(runs_dir, f"{run_id}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", required=True)
    parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    rules_path = os.path.join(args.plan_dir, "rules.json")
    active_run_path = os.path.join(args.plan_dir, "active-run.json")
    if not os.path.exists(rules_path) and not os.path.exists(active_run_path):
        warn(
            "rules.json and active-run.json are both missing; "
            "skipping passive run telemetry"
        )
        return 0

    record = build_record(args.plan_dir, args.run_id, utc_now())
    try:
        write_record(args.plan_dir, args.run_id, record)
    except OSError as exc:
        print(f"error: failed to write run telemetry: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
