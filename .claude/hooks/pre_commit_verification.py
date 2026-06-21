#!/usr/bin/env python3
"""Tier 1 pre-commit TDD ledger verification."""

import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Set


sys.dont_write_bytecode = True
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from tdd_common import entry_status_valid, find_entry, is_code_path, load_ledger  # noqa: E402


PRECOMMIT_ALLOWED = {"pass", "covered_existing", "not_applicable"}


def load_envelope():
    try:
        envelope = json.loads(sys.stdin.read())
    except Exception:
        return None
    if not isinstance(envelope, dict):
        return None
    return envelope


def command_from_envelope(envelope):
    if envelope.get("tool_name") != "Bash":
        return None

    tool_input = envelope.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    return command


def is_git_commit_command(command):
    return re.search(r"(^|[^\w-])git\s+commit(\s|$)", command) is not None


def git_is_repo(project_dir):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def staged_files(project_dir):
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def add_command(commands, seen, command):
    if not isinstance(command, str):
        return
    normalized = command.strip()
    if not normalized or normalized in seen:
        return
    seen.add(normalized)
    commands.append(normalized)


def plan_verification_commands(project_dir):
    plan_dir = os.environ.get("HARNESS_PLAN_DIR")
    if not plan_dir:
        plan_dir = os.path.join(project_dir, ".plan")
    rules_path = os.path.join(plan_dir, "rules.json")
    if not os.path.isfile(rules_path):
        return []

    try:
        with open(rules_path, "r", encoding="utf-8") as rules_file:
            payload = json.load(rules_file)
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        return []
    commands = verification.get("commands")
    if not isinstance(commands, list):
        return []
    return [command.strip() for command in commands if isinstance(command, str) and command.strip()]


def entry_label(entry):
    entry_id = entry.get("id")
    if isinstance(entry_id, str) and entry_id.strip():
        return entry_id.strip()
    return "<unknown>"


def collect_tdd_commands(ledger, rel_paths):
    commands = []
    seen = set()
    checked_entry_ids = set()

    for rel in rel_paths:
        entry = find_entry(ledger, rel)
        if entry is None:
            print("[PreCommit BLOCK] no tdd entry for {}".format(rel), file=sys.stderr)
            return None

        if not entry_status_valid(entry, PRECOMMIT_ALLOWED):
            status = entry.get("status")
            if status == "planned":
                print(
                    "[PreCommit BLOCK] tdd entry for {} is still planned".format(rel),
                    file=sys.stderr,
                )
            else:
                print(
                    "[PreCommit BLOCK] invalid tdd entry for {}".format(rel),
                    file=sys.stderr,
                )
            return None

        stable_id = id(entry)
        if stable_id in checked_entry_ids:
            continue
        checked_entry_ids.add(stable_id)

        if entry.get("status") in ("pass", "covered_existing"):
            add_command(commands, seen, entry.get("test"))

    return commands


def run_commands(project_dir, commands):
    for command in commands:
        print("[PreCommit] running: {}".format(command), file=sys.stderr)
        result = subprocess.run(["/bin/bash", "-lc", command], cwd=project_dir)
        if result.returncode != 0:
            print(
                "[PreCommit BLOCK] verification failed: {}".format(command),
                file=sys.stderr,
            )
            return 2
    return 0


def decide(project_dir):
    if not git_is_repo(project_dir):
        return 0

    try:
        staged = staged_files(project_dir)
    except Exception as exc:
        print("[PreCommit BLOCK] unable to list staged files: {}".format(exc), file=sys.stderr)
        return 2

    code_paths = [path for path in staged if is_code_path(path)]
    if not code_paths:
        return 0

    ledger = load_ledger(project_dir)
    if ledger is None:
        print(
            "[PreCommit BLOCK] create .ai-harness/tasks/tdd.json before committing code paths",
            file=sys.stderr,
        )
        return 2

    commands = collect_tdd_commands(ledger, code_paths)
    if commands is None:
        return 2

    seen = set(commands)
    for command in plan_verification_commands(project_dir):
        add_command(commands, seen, command)

    return run_commands(project_dir, commands)


def main():
    envelope = load_envelope()
    if envelope is None:
        return 0

    command = command_from_envelope(envelope)
    if command is None:
        return 0

    if not is_git_commit_command(command):
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    return decide(project_dir)


if __name__ == "__main__":
    sys.exit(main())
