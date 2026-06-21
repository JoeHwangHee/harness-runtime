#!/usr/bin/env python3
"""Tier 1 prewrite TDD ledger guard."""

import json
import os
import sys


sys.dont_write_bytecode = True
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from tdd_common import entry_status_valid, find_entry, is_code_path, load_ledger, repo_relative  # noqa: E402


PREWRITE_ALLOWED = {"planned", "pass", "covered_existing", "not_applicable"}


def load_envelope():
    try:
        envelope = json.loads(sys.stdin.read())
    except Exception:
        return None
    if not isinstance(envelope, dict):
        return None
    return envelope


def target_path(envelope):
    tool_input = envelope.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    path = tool_input.get("file_path")
    if path is None:
        path = tool_input.get("path")
    if not isinstance(path, str) or not path:
        return None
    return path


def main():
    envelope = load_envelope()
    if envelope is None:
        return 0

    if envelope.get("tool_name") not in ("Edit", "Write"):
        return 0

    path = target_path(envelope)
    if path is None:
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    rel = repo_relative(project_dir, path)
    if not is_code_path(rel):
        return 0

    ledger = load_ledger(project_dir)
    if ledger is None:
        print(
            "[Tier1 BLOCK] create .ai-harness/tasks/tdd.json before editing code paths",
            file=sys.stderr,
        )
        return 2

    entry = find_entry(ledger, rel)
    if entry is None:
        print("[Tier1 BLOCK] no tdd entry for {}".format(rel), file=sys.stderr)
        return 2

    if not entry_status_valid(entry, PREWRITE_ALLOWED):
        print("[Tier1 BLOCK] invalid tdd entry for {}".format(rel), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
