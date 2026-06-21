#!/usr/bin/env python3
"""Inject or update the conditions_hash header in review-brief.md."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.dont_write_bytecode = True

import harness_hash  # noqa: E402


HEADER_RE = re.compile(r"^<!-- conditions_hash: .* -->$")


def inject_brief_hash(plan_dir: str | Path) -> str:
    plan_path = Path(plan_dir)
    brief_path = plan_path / "review-brief.md"
    if not brief_path.exists():
        raise FileNotFoundError(f"{brief_path} does not exist")

    digest = harness_hash.conditions_hash(plan_path)
    header = f"<!-- conditions_hash: {digest} -->"
    text = brief_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    if lines and HEADER_RE.match(lines[0].rstrip("\r\n")):
        newline = "\n"
        if lines[0].endswith("\r\n"):
            newline = "\r\n"
        lines[0] = header + newline
        new_text = "".join(lines)
    else:
        new_text = header + "\n\n" + text

    brief_path.write_text(new_text, encoding="utf-8")
    return digest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inject conditions_hash into a review brief."
    )
    parser.add_argument("--plan-dir", default=".plan")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        print(inject_brief_hash(args.plan_dir))
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
