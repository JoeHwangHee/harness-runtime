#!/usr/bin/env python3
"""Write review-pass.json for a plan directory."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.dont_write_bytecode = True

import harness_hash  # noqa: E402


def write_review_pass(plan_dir: str | Path, verdict: str) -> dict[str, str]:
    if verdict != "pass":
        raise ValueError("only --verdict pass is supported")

    plan_path = Path(plan_dir)
    plan_file = plan_path / "plan.md"
    brief_file = plan_path / "review-brief.md"

    missing = [str(path) for path in (plan_file, brief_file) if not path.exists()]
    if missing:
        raise FileNotFoundError(", ".join(missing))

    marker = {
        "plan_hash": harness_hash.file_hash(plan_file),
        "brief_hash": harness_hash.file_hash(brief_file),
        "verdict": verdict,
        "ts": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }

    marker_path = plan_path / "review-pass.json"
    marker_path.write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return marker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a review-pass marker.")
    parser.add_argument("--plan-dir", default=".plan")
    parser.add_argument("--verdict", required=True, choices=["pass"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        marker = write_review_pass(args.plan_dir, args.verdict)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(marker, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
