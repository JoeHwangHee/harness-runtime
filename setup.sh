#!/usr/bin/env bash
# setup.sh — 통합 의도→강제 하네스를 새/기존 레포에 부트스트랩.
#
# 멱등(idempotent). 몇 번을 돌려도 안전 — 기존 파일을 덮어쓰지 않는다.
# 마지막에 Codex 파생물을 SoT(CLAUDE.md)에서 재생성하고 stale을 검사한다.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say()  { printf '%s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }

say "harness setup ▸ root=$ROOT"

# 1. 모든 훅을 실행 가능으로.
if [ -d .claude/hooks ]; then
  chmod +x .claude/hooks/*.sh 2>/dev/null || true
  say "✓ 훅 스크립트 실행권한 부여"
fi
# 생성기도 실행 가능으로.
[ -f .ai-harness/scripts/generate_codex_derivatives.sh ] && chmod +x .ai-harness/scripts/generate_codex_derivatives.sh 2>/dev/null || true

# 2. Tier1 원장 시드 (없을 때만 — 덮어쓰지 않음).
if [ ! -f .ai-harness/tasks/tdd.json ]; then
  mkdir -p .ai-harness/tasks
  printf '{ "version": 1, "entries": [] }\n' > .ai-harness/tasks/tdd.json
  say "✓ .ai-harness/tasks/tdd.json 생성 (빈 원장)"
else
  say "• .ai-harness/tasks/tdd.json 이미 존재 — 유지"
fi

# 3. Codex 파생물 재생성 (CLAUDE.md SoT → AGENTS.md·.codex/).
if [ -f .ai-harness/scripts/generate_codex_derivatives.py ] && [ -f CLAUDE.md ]; then
  if python3 .ai-harness/scripts/generate_codex_derivatives.py; then
    say "✓ Codex 파생물 재생성 (AGENTS.md·.codex/)"
  else
    warn "Codex 파생물 생성 실패 — 수동 확인 필요"
  fi
  # stale 검사 (생성 직후엔 통과해야 정상).
  if python3 .ai-harness/scripts/generate_codex_derivatives.py --check; then
    say "✓ 파생물 stale 검사 통과"
  else
    warn "파생물이 SoT와 어긋남 — 위 메시지 확인 후 재생성"
  fi
else
  warn "CLAUDE.md 또는 생성기 부재 — 파생 단계 건너뜀"
fi

# 4. Post-clone 체크리스트.
say
say "Post-clone 체크리스트:"
say "  [1] CLAUDE.md(SoT)의 가족/스코프를 프로젝트에 맞게 수정"
say "  [2] .ai-harness/{deny-list.json,tdd-matrix.md} 정책을 프로젝트에 맞게 검토"
say "  [3] ./setup.sh 재실행 (파생물 stale 검사 통과 확인)"
say "  [4] Claude Code:  claude .    /  Codex CLI:  codex"
say
say "두 CLI 모두 다음 실행 시 훅을 자동 로드한다. (AGENTS.md·.codex/는 생성물 — 손대지 말 것)"
