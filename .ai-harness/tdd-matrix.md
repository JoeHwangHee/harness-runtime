# Tier 1 Minimal TDD Policy

Tier 1 is a repository-wide, semi-static TDD gate for code-path edits.

Code paths are repo-relative files that start with `src/`, `app/`, or `lib/` and end with one of: `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.rb`, `.go`, `.rs`, `.java`, `.kt`, `.swift`, `.c`, `.cc`, `.cpp`, `.h`, `.hpp`, `.sql`.

Non-code paths such as `docs/`, `scripts/`, `.ai-harness/scripts/`, `.claude/`, and README files do not trigger the Tier 1 guard.

Ledger path: `.ai-harness/tasks/tdd.json`.

Ledger schema:

```json
{
  "version": 1,
  "entries": [
    {
      "id": "<slug>",
      "targets": ["<glob>", "..."],
      "test": "<runnable cmd>",
      "status": "planned|pass|covered_existing|not_applicable",
      "reason": "<required when not_applicable>"
    }
  ]
}
```

`targets` are matched with Python `fnmatch`; `**` is normalized to `*`.

Status meanings:
- `planned`: allowed before write, but blocked before commit.
- `pass`: test was run and passed; `test` is required.
- `covered_existing`: existing tests cover the target; `test` is required.
- `not_applicable`: no test applies; `reason` is required.

`tdd-guard` runs before writes and requires a ledger entry for code paths.

`pre-commit-verification` runs before commits and blocks planned or unverified code-path entries, then executes required verification commands.

This harness intentionally does not introduce the 12-category composite matrix.
