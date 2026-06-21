#!/usr/bin/env python3
"""Canonical hash helpers for harness artifacts.

Definitions:

file_hash(path) = "sha256:" + sha256(file bytes).hexdigest()

conditions_hash(plan_dir):
    parts = []
    for name in ["goal.md", "spec.md", "conventions.md", "gotchas.md"]:
        p = plan_dir / name
        b = p.read_bytes() if p.exists() else b""
        parts.append(name + ":" + sha256(b).hexdigest())
    conditions_hash = "sha256:" + sha256(
        "\\n".join(parts).encode("utf-8")
    ).hexdigest()

Missing condition files are treated as empty bytes for deterministic output.
"""

from __future__ import annotations

import argparse
import sys
from hashlib import sha256
from pathlib import Path


CONDITION_FILES = ["goal.md", "spec.md", "conventions.md", "gotchas.md"]


def file_hash(path: str | Path) -> str:
    """Return the sha256-prefixed hash of a file's raw bytes."""
    return "sha256:" + sha256(Path(path).read_bytes()).hexdigest()


def conditions_hash(plan_dir: str | Path) -> str:
    """Return the canonical hash of condition files in a plan directory."""
    plan_path = Path(plan_dir)
    parts = []
    for name in CONDITION_FILES:
        path = plan_path / name
        data = path.read_bytes() if path.exists() else b""
        parts.append(name + ":" + sha256(data).hexdigest())
    return "sha256:" + sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    file_parser = subparsers.add_parser("file", help="hash a file")
    file_parser.add_argument("path")

    conditions_parser = subparsers.add_parser(
        "conditions", help="hash plan condition files"
    )
    conditions_parser.add_argument("plan_dir")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "file":
            print(file_hash(args.path))
        elif args.command == "conditions":
            print(conditions_hash(args.plan_dir))
        else:
            parser.error(f"unknown command: {args.command}")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
