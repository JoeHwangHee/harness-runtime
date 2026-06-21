#!/usr/bin/env python3
"""Write operational state contracts.

Invariant: state transitions happen only by evidence recomputation, not by
assigning trusted status values. This prevents callers from self-grading a
test or review by writing satisfied/pass directly.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.dont_write_bytecode = True

import harness_hash  # noqa: E402


REVIEW_LANES = {"go", "reviewer"}


class ContractError(Exception):
    """Expected user-facing contract writer failure."""


def print_error(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContractError(f"missing required file: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ContractError(f"failed to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return payload


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as exc:
        raise ContractError(f"failed to write {path}: {exc}") from exc


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def required_tests_from_rules(rules_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rules = rules_payload.get("rules")
    if not isinstance(rules, list):
        raise ContractError("rules.json must contain a top-level rules array")

    required_tests: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict) or "requires_test" not in rule:
            continue
        if "id" not in rule:
            raise ContractError("rule with requires_test is missing id")
        required_tests.append(
            {
                "rule_id": rule["id"],
                "test_glob": rule["requires_test"],
                "status": "declared",
            }
        )
    return required_tests


def seed_ledger(args: argparse.Namespace) -> int:
    plan_dir = Path(args.plan_dir)
    rules_payload = load_json_object(plan_dir / "rules.json")
    ledger = {
        "run_id": args.run_id,
        "required_tests": required_tests_from_rules(rules_payload),
    }
    write_json_file(plan_dir / "test-ledger.json", ledger)
    print_json(ledger)
    return 0


def init_run(args: argparse.Namespace) -> int:
    plan_dir = Path(args.plan_dir)
    active_run = {
        "run_id": args.run_id,
        "status": "running",
        "started_ts": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "ttl": args.ttl,
        "contract_root": args.contract_root,
        "worktree_root": args.worktree_root,
        "rules_hash": args.rules_hash,
    }
    write_json_file(plan_dir / "active-run.json", active_run)
    print_json(active_run)
    return 0


def ledger_entries(ledger: dict[str, Any], path: Path) -> list[Any]:
    entries = ledger.get("required_tests")
    if not isinstance(entries, list):
        raise ContractError(f"{path} must contain a required_tests array")
    return entries


def mark_satisfied(args: argparse.Namespace) -> int:
    plan_dir = Path(args.plan_dir)
    ledger_path = plan_dir / "test-ledger.json"
    ledger = load_json_object(ledger_path)
    entries = ledger_entries(ledger, ledger_path)

    target: dict[str, Any] | None = None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("rule_id") == args.rule_id:
            target = entry
            break
    if target is None:
        return print_error(f"rule not found: {args.rule_id}")

    matches = sorted(glob.glob(args.test_glob))
    if not matches:
        return print_error("missing-test-file")

    result = subprocess.run(args.test_cmd, shell=True)
    if result.returncode != 0:
        return print_error(f"test-failed exit={result.returncode}")

    target["status"] = "satisfied"
    target["evidence"] = {
        "file": matches[0],
        "cmd": args.test_cmd,
        "exit_code": 0,
    }
    write_json_file(ledger_path, ledger)
    print(f"satisfied: {args.rule_id}")
    return 0


def load_rules_hash(plan_dir: Path) -> str:
    active_run_path = plan_dir / "active-run.json"
    if not active_run_path.exists():
        return ""
    active_run = load_json_object(active_run_path)
    rules_hash = active_run.get("rules_hash", "")
    return rules_hash if isinstance(rules_hash, str) else ""


def review_record(args: argparse.Namespace) -> int:
    if args.lane not in REVIEW_LANES:
        return print_error(f"lane '{args.lane}' not permitted for review-record")

    plan_dir = Path(args.plan_dir)
    reviewer_output_path = Path(args.reviewer_output)
    diff_path = Path(args.diff_file)
    reviewer_output = load_json_object(reviewer_output_path)

    reviewer_checks = reviewer_output.get("reviewer_checks")
    if not isinstance(reviewer_checks, list):
        raise ContractError("reviewer-output must contain a reviewer_checks array")

    final_diff_verdict = reviewer_output.get("final_diff_verdict")
    verdict = (
        "pass"
        if all(
            isinstance(check, dict) and check.get("verdict") == "pass"
            for check in reviewer_checks
        )
        and final_diff_verdict == "pass"
        else "fail"
    )

    final_review = {
        "run_id": args.run_id,
        "rules_hash": load_rules_hash(plan_dir),
        "diff_hash": harness_hash.file_hash(diff_path),
        "verification_hash": harness_hash.file_hash(plan_dir / "test-ledger.json"),
        "reviewer_session_id": reviewer_output.get("reviewer_session_id", ""),
        "reviewer_output_hash": harness_hash.file_hash(reviewer_output_path),
        "reviewer_checks": reviewer_checks,
        "final_diff_verdict": final_diff_verdict,
        "verdict": verdict,
    }
    write_json_file(plan_dir / "final-review-pass.json", final_review)
    print_json(final_review)
    return 0


def cannot_mark_done(reason: str) -> int:
    return print_error(f"cannot mark done: {reason}")


def done_gate_reason(plan_dir: Path, active_run: dict[str, Any], diff_file: str | None) -> str | None:
    ledger_path = plan_dir / "test-ledger.json"
    ledger = load_json_object(ledger_path)
    entries = ledger_entries(ledger, ledger_path)
    if any(not isinstance(entry, dict) or entry.get("status") != "satisfied" for entry in entries):
        return "declared-remaining"

    final_review_path = plan_dir / "final-review-pass.json"
    if not final_review_path.exists():
        return "review-not-pass"
    final_review = load_json_object(final_review_path)
    if final_review.get("verdict") != "pass":
        return "review-not-pass"

    if not diff_file:
        return "stale-diff"
    if final_review.get("diff_hash") != harness_hash.file_hash(diff_file):
        return "stale-diff"
    if final_review.get("rules_hash") != active_run.get("rules_hash"):
        return "rules-hash-drift"
    return None


def run_state(args: argparse.Namespace) -> int:
    plan_dir = Path(args.plan_dir)
    active_run_path = plan_dir / "active-run.json"
    active_run = load_json_object(active_run_path)

    if args.status == "done":
        reason = done_gate_reason(plan_dir, active_run, args.diff_file)
        if reason is not None:
            return cannot_mark_done(reason)
        active_run["status"] = "done"
        write_json_file(active_run_path, active_run)
        print("done")
        return 0

    active_run["status"] = args.status
    write_json_file(active_run_path, active_run)
    print(args.status)
    return 0


def add_plan_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan-dir", default=".plan")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed-ledger")
    add_plan_dir(seed)
    seed.add_argument("--run-id", required=True)
    seed.set_defaults(func=seed_ledger)

    init = subparsers.add_parser("init-run")
    add_plan_dir(init)
    init.add_argument("--run-id", required=True)
    init.add_argument("--contract-root", required=True)
    init.add_argument("--worktree-root", required=True)
    init.add_argument("--rules-hash", required=True)
    init.add_argument("--ttl", type=int, default=3600)
    init.set_defaults(func=init_run)

    satisfied = subparsers.add_parser("mark-satisfied")
    add_plan_dir(satisfied)
    satisfied.add_argument("--rule-id", required=True)
    satisfied.add_argument("--test-glob", required=True)
    satisfied.add_argument("--test-cmd", required=True)
    satisfied.set_defaults(func=mark_satisfied)

    review = subparsers.add_parser("review-record")
    add_plan_dir(review)
    review.add_argument("--run-id", required=True)
    review.add_argument("--lane", required=True)
    review.add_argument("--reviewer-output", required=True)
    review.add_argument("--diff-file", required=True)
    review.set_defaults(func=review_record)

    state = subparsers.add_parser("run-state")
    add_plan_dir(state)
    state.add_argument("--run-id", required=True)
    state.add_argument("--status", required=True, choices=["running", "done", "aborted"])
    state.add_argument("--diff-file")
    state.set_defaults(func=run_state)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except ContractError as exc:
        return print_error(str(exc))
    except OSError as exc:
        return print_error(f"error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
