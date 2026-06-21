<!-- GENERATED FILE: edit `.ai-harness/harness-contract.md` / .claude/settings.json and rerun .ai-harness/scripts/generate_codex_derivatives.sh -->
<!-- sot_hash: sha256:3601b25bd28b57fcfcee14a1b30a8a9ae06c7bb876f21317b685f33ff5f2b131 -->
<!-- settings_hash: sha256:e9cbf09274481e10fdb2347ebf1c680c65dd6c624939bc8be942d835de66e737 -->

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
