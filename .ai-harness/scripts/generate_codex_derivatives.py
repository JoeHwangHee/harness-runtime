#!/usr/bin/env python3
"""Generate Codex derivative files from the Claude source of truth."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DERIVATIVES = [
    Path("AGENTS.md"),
    Path(".codex/config.toml"),
    Path(".codex/hooks.json"),
    Path(".codex/README.md"),
]

HASH_RE = re.compile(r"\b(sot_hash|settings_hash):\s*(sha256:[0-9a-f]{64})\b")


def resolve_root() -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return handle.read()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def hash_file(root: Path, path: Path) -> str:
    hash_script = root / ".ai-harness" / "scripts" / "harness_hash.py"
    proc = subprocess.run(
        [sys.executable, str(hash_script), "file", str(path)],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        return ""
    return proc.stdout.strip()


def load_settings(root: Path) -> Dict[str, Any]:
    path = root / ".claude" / "settings.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_command(command: str, root: Path) -> str:
    claude_prefix = "$CLAUDE_PROJECT_DIR/"
    if command.startswith(claude_prefix):
        return command[len(claude_prefix) :]

    root_prefix = str(root) + "/"
    if command.startswith(root_prefix):
        return command[len(root_prefix) :]

    return command


def normalize_commands(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        normalized: Dict[str, Any] = {}
        for key, item in value.items():
            if key == "command" and isinstance(item, str):
                normalized[key] = normalize_command(item, root)
            else:
                normalized[key] = normalize_commands(item, root)
        return normalized
    if isinstance(value, list):
        return [normalize_commands(item, root) for item in value]
    return value


def discover_skills(root: Path) -> List[str]:
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    names = [
        child.name
        for child in skills_dir.iterdir()
        if child.is_dir() and not child.name.endswith("-workspace")
    ]
    return sorted(names)


def render_agents(sot_hash: str, settings_hash: str, skills: Iterable[str]) -> str:
    skill_list = ", ".join("`%s`" % name for name in skills) or "(none found)"
    return """<!-- GENERATED FILE: edit `.ai-harness/harness-contract.md` and rerun .ai-harness/scripts/generate_codex_derivatives.sh -->
<!-- sot_hash: {sot_hash} -->
<!-- settings_hash: {settings_hash} -->

# Codex Project Instructions

## Source Of Truth
- Edit `.ai-harness/harness-contract.md`, `.claude/skills/`, and `.claude/agents/`; then rerun `.ai-harness/scripts/generate_codex_derivatives.sh`.
- Do not hand-edit `AGENTS.md` or files under `.codex/`.
- Treat generated headers as freshness markers. If they disagree with current source hashes, regenerate before relying on these files.

## Required Reads
- Always read `docs/harness-design.md` and `docs/contracts.md` before harness work.
- If an active run exists, also read `.plan/plan.md`, `.plan/rules.json`, and `.plan/active-run.json`.
- For skill-driven work, read the relevant `.claude/skills/<name>/SKILL.md` before acting.

## Pipeline \u2460-\u2465
1. \u2460 Draft `.plan/plan.md` with steps, declared surfaces, and dependencies.
2. \u2461 Run `goal-interview` to capture `goal.md`, `spec.md`, `conventions.md`, and `gotchas.md`.
3. \u2462 Run `review-brief` as a cold, plan-blind refinement anchored to the captured conditions.
4. \u2463 Run `plan-review` to check the main plan against the anchored brief and emit `review-pass.json`.
5. \u2464 Run `rules-gen` to compile the approved plan and conditions into `.plan/rules.json` plus `rules-pass.json`.
6. \u2465 Run `go` only after approval; it seeds execution state, enforces the rules, collects evidence, and closes through final review.

## Enforcement Model
- Tier 0 is the always-on static safety floor: catastrophic shell and protected-path patterns are blocked by `.claude/hooks/pre-tool-use.sh`.
- Tier 1 is project TDD policy: code-path edits require ledger coverage and pre-commit verification.
- Tier 2 is plan scope: `.plan/rules.json` freezes declared surfaces and blocks out-of-scope edits.
- Hook order is Tier 0 -> Tier 1 -> Tier 2. Any hard block stops the tool call.
- Hooks are syntactic guardrails only. Runtime meaning, gotchas, smoke checks, merge readiness, and final judgment come from `go` gates plus cold review.

## Dual CLI Position
- Claude Code centers enforcement on PreToolUse hard blocks from `.claude/settings.json`.
- Codex uses the same hook scripts as guardrails, plus `.codex/config.toml` sandbox and approval permissions, `go` verification gates, and final-review synthesis.
- `.codex/hooks.json` mirrors only the Codex-supported `PreToolUse` surface from `.claude/settings.json`.

## Skills
- Available `.claude/skills/` entries, excluding `*-workspace`: {skill_list}.
- Expected harness flow uses `goal-interview`, `review-brief`, `plan-review`, `rules-gen`, and `go`.
""".format(
        sot_hash=sot_hash,
        settings_hash=settings_hash,
        skill_list=skill_list,
    )


def render_config(sot_hash: str, settings_hash: str) -> str:
    return """# GENERATED FILE: edit `.ai-harness/harness-contract.md` / .claude/settings.json and rerun .ai-harness/scripts/generate_codex_derivatives.sh
# sot_hash: {sot_hash}
# settings_hash: {settings_hash}

approval_policy = "on-request"
sandbox_mode = "workspace-write"
project_doc_fallback_filenames = ["AGENTS.md"]
project_doc_max_bytes = 32768

[features]
codex_hooks = true
hooks = true
""".format(
        sot_hash=sot_hash,
        settings_hash=settings_hash,
    )


def render_hooks(root: Path, sot_hash: str, settings_hash: str) -> str:
    settings = load_settings(root)
    pre_tool_use = settings.get("hooks", {}).get("PreToolUse", [])
    hooks = {
        "//": [
            "GENERATED - Codex mirrors only supported PreToolUse events; regenerate to update.",
            "sot_hash: %s" % sot_hash,
            "settings_hash: %s" % settings_hash,
        ],
        "hooks": {
            "PreToolUse": normalize_commands(pre_tool_use, root),
        },
    }
    return json.dumps(hooks, ensure_ascii=False, indent=2) + "\n"


def render_readme(sot_hash: str, settings_hash: str) -> str:
    return """<!-- GENERATED FILE: edit `.ai-harness/harness-contract.md` / .claude/settings.json and rerun .ai-harness/scripts/generate_codex_derivatives.sh -->
<!-- sot_hash: {sot_hash} -->
<!-- settings_hash: {settings_hash} -->

# Codex Derivatives

These files are generated from `.ai-harness/harness-contract.md` and `.claude/settings.json`. Edit those source files and rerun `.ai-harness/scripts/generate_codex_derivatives.sh`; do not edit `.codex/hooks.json` directly.

| Event | Status | Target |
|---|---|---|
| `PreToolUse` | active | mirrors `.claude/settings.json` commands to `.claude/hooks/*.sh` |
| `PostToolUse` | reserved | not generated |
| `PreCompact` | reserved | not generated |
| `PostCompact` | reserved | not generated |
| `SessionStart` | reserved | not generated |
| `UserPromptSubmit` | reserved | not generated |
| `Stop` | reserved | not generated |
| `PermissionRequest` | reserved | not generated |

Wire format: hooks read stdin JSON fields `tool_name`, `tool_input.command`, `tool_input.file_path`, and `tool_input.path`; Codex `apply_patch` uses `tool_input.path`.
""".format(
        sot_hash=sot_hash,
        settings_hash=settings_hash,
    )


def expected_hashes(root: Path) -> Tuple[str, str]:
    sot = root / ".ai-harness" / "harness-contract.md"
    settings = root / ".claude" / "settings.json"
    if not sot.is_file():
        print("ERROR: .ai-harness/harness-contract.md not found.", file=sys.stderr)
        raise SystemExit(1)
    if not settings.is_file():
        print("ERROR: .claude/settings.json not found.", file=sys.stderr)
        raise SystemExit(1)

    sot_hash = hash_file(root, sot)
    settings_hash = hash_file(root, settings)
    if not sot_hash or not settings_hash:
        raise SystemExit(1)
    return sot_hash, settings_hash


def extract_hashes(path: Path) -> Dict[str, str]:
    if path.name == "hooks.json":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        comments = data.get("//", [])
        if not isinstance(comments, list):
            comments = []
        text = "\n".join(str(item) for item in comments)
    else:
        text = read_text(path)
    return dict(HASH_RE.findall(text))


def check_derivatives(root: Path, sot_hash: str, settings_hash: str) -> int:
    stale: List[str] = []
    expected = {
        "sot_hash": sot_hash,
        "settings_hash": settings_hash,
    }

    for rel in DERIVATIVES:
        path = root / rel
        if not path.exists():
            stale.append("%s missing" % rel)
            continue
        try:
            actual = extract_hashes(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            stale.append("%s unreadable: %s" % (rel, exc))
            continue

        for key, value in expected.items():
            if actual.get(key) != value:
                stale.append(
                    "%s %s stale (found %s, expected %s)"
                    % (rel, key, actual.get(key, "missing"), value)
                )

    if stale:
        for item in stale:
            print("stale: %s" % item, file=sys.stderr)
        return 3
    return 0


def generate(root: Path, sot_hash: str, settings_hash: str) -> None:
    outputs = {
        Path("AGENTS.md"): render_agents(
            sot_hash,
            settings_hash,
            discover_skills(root),
        ),
        Path(".codex/config.toml"): render_config(sot_hash, settings_hash),
        Path(".codex/hooks.json"): render_hooks(root, sot_hash, settings_hash),
        Path(".codex/README.md"): render_readme(sot_hash, settings_hash),
    }
    for rel, content in outputs.items():
        write_text(root / rel, content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Codex derivative files from .ai-harness/harness-contract.md."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check generated files for stale source hashes without writing",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = resolve_root()
    sot_hash, settings_hash = expected_hashes(root)

    if args.check:
        return check_derivatives(root, sot_hash, settings_hash)

    generate(root, sot_hash, settings_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
