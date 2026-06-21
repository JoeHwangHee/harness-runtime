#!/usr/bin/env python3
"""Derive structural parallelism potential from a plan's Step/Depends graph."""
from __future__ import annotations

import argparse
import json
import re
import sys


STEP_HEADING_RE = re.compile(r"^##\s+(Step\s+\S+?)\s*:")
DEPENDS_RE = re.compile(r"^Depends:\s*(.*)$")


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _parse_depends(raw_depends: str | None) -> list[str]:
    if raw_depends is None:
        return []

    stripped = raw_depends.strip()
    if stripped == "" or stripped == "-" or stripped.lower() == "none":
        return []

    depends = []
    for token in raw_depends.split(","):
        normalized = _collapse_whitespace(token.strip())
        if normalized:
            depends.append(normalized)
    return depends


def parse_plan_steps(plan_text: str) -> list[dict]:
    lines = plan_text.splitlines()
    headings = []
    for index, line in enumerate(lines):
        match = STEP_HEADING_RE.match(line)
        if match:
            headings.append((index, _collapse_whitespace(match.group(1))))

    steps = []
    for offset, (start_index, step_id) in enumerate(headings):
        end_index = headings[offset + 1][0] if offset + 1 < len(headings) else len(lines)
        raw_depends = None
        for line in lines[start_index + 1 : end_index]:
            match = DEPENDS_RE.match(line)
            if match:
                raw_depends = match.group(1)
                break
        steps.append({"id": step_id, "depends": _parse_depends(raw_depends)})
    return steps


def analyze_parallelism(steps: list[dict]) -> dict:
    ids = [s["id"] for s in steps]
    id_set = set(ids)
    depends_of = {s["id"]: list(s["depends"]) for s in steps}

    for step in steps:
        step_id = step["id"]
        for dependency in step["depends"]:
            if dependency not in id_set:
                raise ValueError(f"dangling dependency: {dependency} (referenced by {step_id})")

    remaining = list(ids)
    resolved = set()
    waves = []
    while remaining:
        wave = [n for n in remaining if all(d in resolved for d in depends_of[n])]
        if not wave:
            raise ValueError("dependency cycle detected")
        waves.append(wave)
        resolved.update(wave)
        remaining = [n for n in remaining if n not in resolved]

    task_count = len(ids)
    serial_cost = task_count
    wave_count = len(waves)
    parallelism_ratio = round(serial_cost / wave_count, 4) if wave_count else 0.0
    max_wave_width = max((len(w) for w in waves), default=0)

    return {
        "task_count": task_count,
        "serial_cost": serial_cost,
        "wave_count": wave_count,
        "parallelism_ratio": parallelism_ratio,
        "max_wave_width": max_wave_width,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args(argv)

    try:
        with open(args.plan, "r", encoding="utf-8") as plan_file:
            steps = parse_plan_steps(plan_file.read())
        result = analyze_parallelism(steps)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
