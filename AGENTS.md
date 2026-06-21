<!-- GENERATED FILE: edit `.ai-harness/harness-contract.md` and rerun .ai-harness/scripts/generate_codex_derivatives.sh -->
<!-- sot_hash: sha256:3601b25bd28b57fcfcee14a1b30a8a9ae06c7bb876f21317b685f33ff5f2b131 -->
<!-- settings_hash: sha256:e9cbf09274481e10fdb2347ebf1c680c65dd6c624939bc8be942d835de66e737 -->

# Codex Project Instructions

## Source Of Truth
- Edit `.ai-harness/harness-contract.md`, `.claude/skills/`, and `.claude/agents/`; then rerun `.ai-harness/scripts/generate_codex_derivatives.sh`.
- Do not hand-edit `AGENTS.md` or files under `.codex/`.
- Treat generated headers as freshness markers. If they disagree with current source hashes, regenerate before relying on these files.

## Required Reads
- Always read `docs/harness-design.md` and `docs/contracts.md` before harness work.
- If an active run exists, also read `.plan/plan.md`, `.plan/rules.json`, and `.plan/active-run.json`.
- For skill-driven work, read the relevant `.claude/skills/<name>/SKILL.md` before acting.

## Pipeline ①-⑥
1. ① Draft `.plan/plan.md` with steps, declared surfaces, and dependencies.
2. ② Run `goal-interview` to capture `goal.md`, `spec.md`, `conventions.md`, and `gotchas.md`.
3. ③ Run `review-brief` as a cold, plan-blind refinement anchored to the captured conditions.
4. ④ Run `plan-review` to check the main plan against the anchored brief and emit `review-pass.json`.
5. ⑤ Run `rules-gen` to compile the approved plan and conditions into `.plan/rules.json` plus `rules-pass.json`.
6. ⑥ Run `go` only after approval; it seeds execution state, enforces the rules, collects evidence, and closes through final review.

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
- Available `.claude/skills/` entries, excluding `*-workspace`: `go`, `goal-interview`, `plan-review`, `review-brief`, `rules-gen`, `transplant`.
- Expected harness flow uses `goal-interview`, `review-brief`, `plan-review`, `rules-gen`, and `go`.
