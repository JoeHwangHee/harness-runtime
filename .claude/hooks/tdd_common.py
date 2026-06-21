#!/usr/bin/env python3
"""Shared helpers for the minimal Tier 1 TDD ledger gates."""

import fnmatch
import json
import os
from typing import Any, Dict, Optional, Set


CODE_PATH_PREFIXES = ("src/", "app/", "lib/")
IMPL_SUFFIXES = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sql",
)


def _slash(path: str) -> str:
    return path.replace("\\", "/")


def repo_relative(project_dir: str, path: str) -> str:
    if not isinstance(path, str):
        return ""

    raw = path.strip()
    if not raw:
        return ""

    project_abs = os.path.abspath(project_dir or ".")
    raw_slash = _slash(raw)
    project_slash = _slash(project_abs)

    if os.path.isabs(raw):
        rel = os.path.relpath(raw, project_abs)
    elif raw_slash.startswith(project_slash + "/"):
        rel = raw_slash[len(project_slash) + 1 :]
    else:
        rel = raw

    rel = _slash(os.path.normpath(rel))
    if rel == ".":
        return ""
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def is_code_path(rel: str) -> bool:
    if not isinstance(rel, str):
        return False

    norm = _slash(os.path.normpath(rel.strip()))
    while norm.startswith("./"):
        norm = norm[2:]

    return norm.startswith(CODE_PATH_PREFIXES) and norm.endswith(IMPL_SUFFIXES)


def load_ledger(project_dir: str) -> Optional[Dict[str, Any]]:
    ledger_path = os.path.join(project_dir or ".", ".ai-harness", "tasks", "tdd.json")
    try:
        with open(ledger_path, "r", encoding="utf-8") as ledger_file:
            ledger = json.load(ledger_file)
    except Exception:
        return None

    if not isinstance(ledger, dict):
        return None
    if not isinstance(ledger.get("entries"), list):
        return None
    return ledger


def _target_matches(target: str, rel: str) -> bool:
    pattern = _slash(target.strip()).replace("**", "*")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    return bool(pattern) and fnmatch.fnmatch(rel, pattern)


def find_entry(ledger: Dict[str, Any], rel: str) -> Optional[Dict[str, Any]]:
    if not isinstance(ledger, dict):
        return None

    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return None

    norm_rel = _slash(os.path.normpath(rel.strip()))
    while norm_rel.startswith("./"):
        norm_rel = norm_rel[2:]

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        targets = entry.get("targets")
        if not isinstance(targets, list):
            continue
        for target in targets:
            if isinstance(target, str) and _target_matches(target, norm_rel):
                return entry
    return None


def entry_status_valid(entry: Dict[str, Any], allowed: Set[str]) -> bool:
    if not isinstance(entry, dict):
        return False

    status = entry.get("status")
    if status not in allowed:
        return False

    if status in ("pass", "covered_existing"):
        test = entry.get("test")
        return isinstance(test, str) and bool(test.strip())

    if status == "not_applicable":
        reason = entry.get("reason")
        return isinstance(reason, str) and bool(reason.strip())

    return True
