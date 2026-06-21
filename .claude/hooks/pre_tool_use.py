#!/usr/bin/env python3
"""
Tier 0 static deny-list guard for Claude PreToolUse envelopes.
Exit 2 blocks a matching catastrophic pattern; malformed inputs fail open.
"""

import json
import os
import re
import sys


def load_envelope():
    try:
        envelope = json.loads(sys.stdin.read())
    except Exception:
        return None

    if not isinstance(envelope, dict):
        return None

    return envelope


def subject_from_envelope(envelope):
    tool_name = envelope.get("tool_name")
    tool_input = envelope.get("tool_input")
    if not isinstance(tool_input, dict):
        return None, None

    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not command:
            return None, None
        return "command", command

    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path")
        if path is None:
            path = tool_input.get("path")
        if not isinstance(path, str) or not path:
            return None, None
        return "path", path

    return None, None


def load_rules():
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    deny_list_path = os.path.join(project_dir, ".ai-harness", "deny-list.json")

    try:
        with open(deny_list_path, "r", encoding="utf-8") as deny_list_file:
            deny_list = json.load(deny_list_file)
    except Exception:
        return []

    if not isinstance(deny_list, dict):
        return []

    rules = deny_list.get("rules", [])
    if not isinstance(rules, list):
        return []

    return [rule for rule in rules if isinstance(rule, dict)]


def rule_text(rule, key):
    value = rule.get(key, "")
    if isinstance(value, str):
        return value
    return ""


def apply_rules(subject_kind, subject):
    for rule in load_rules():
        if rule.get("subject") != subject_kind:
            continue

        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            continue

        try:
            matched = re.search(pattern, subject)
        except re.error:
            continue

        if not matched:
            continue

        rule_id = rule_text(rule, "id")
        reason = rule_text(rule, "reason")
        severity = rule.get("severity")

        if severity == "block":
            print(
                "[Tier0 BLOCK] deny-list[{}] {}".format(rule_id, reason),
                file=sys.stderr,
            )
            return 2

        if severity == "warn":
            print(
                "[Tier0 WARN] deny-list[{}] {}".format(rule_id, reason),
                file=sys.stderr,
            )

    return 0


def main():
    envelope = load_envelope()
    if envelope is None:
        return 0

    subject_kind, subject = subject_from_envelope(envelope)
    if subject_kind is None:
        return 0

    return apply_rules(subject_kind, subject)


if __name__ == "__main__":
    sys.exit(main())
