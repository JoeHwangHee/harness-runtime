#!/usr/bin/env bash
# transplant.sh — 하네스를 기존 프로젝트(host)에 이식. 멱등.
set -euo pipefail
HROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"   # 레포 루트(.ai-harness의 부모)
HOST="${1:-$PWD}"; HOST="$(cd -- "$HOST" && pwd)"
PY=python3
LIB="$HROOT/.ai-harness/scripts/transplant_lib.py"
say() { printf '%s\n' "$*"; }

# 1. 본체 복사 (기존 파일 미덮어씀; settings.json은 §3 병합)
#    버킷 A 정의는 list_runtime_files.sh가 단일 진실원천(AGENTS.md 포함).
while IFS= read -r f; do
  dest="$HOST/$f"
  if [ ! -e "$dest" ]; then mkdir -p "$(dirname "$dest")"; cp "$HROOT/$f" "$dest"; fi
done < <(bash "$HROOT/.ai-harness/scripts/list_runtime_files.sh" "$HROOT")
chmod +x "$HOST/.claude/hooks/"*.sh 2>/dev/null || true
[ -f "$HOST/.ai-harness/tasks/tdd.json" ] || { mkdir -p "$HOST/.ai-harness/tasks"; printf '{ "version": 1, "entries": [] }\n' > "$HOST/.ai-harness/tasks/tdd.json"; }

# 2. CLAUDE.md: 있으면 import 주입, 없으면 스터브
if [ -f "$HOST/CLAUDE.md" ]; then
  "$PY" "$LIB" inject-import "$HOST/CLAUDE.md"
else
  "$PY" "$LIB" stub "$(basename "$HOST")" "$HOST/CLAUDE.md"
  say "HARNESS_TRANSPLANT_STUB_CREATED=1"
fi

# 3. settings.json 병합
"$PY" "$LIB" merge-settings "$HOST/.claude/settings.json" "$HROOT/.claude/settings.json"

# 4. VCS ignore — 하네스 전체를 host VCS에서 로컬 제외
if [ -d "$HOST/.git" ]; then
  mkdir -p "$HOST/.git/info"
  "$PY" "$LIB" exclude "$HOST/.git/info/exclude"
  say "✓ git: .git/info/exclude에 하네스 경로 추가(로컬 전용)"
elif [ -d "$HOST/.svn" ]; then
  say "[WARN] svn 감지 — svn:ignore는 버전관리되는 속성이라 로컬 전용 불가."
  say "       ~/.subversion/config 의 global-ignores에 다음을 추가하세요:"
  say "       .ai-harness .claude .codex AGENTS.md .plan"
else
  say "[WARN] git/svn 미감지 — VCS ignore 건너뜀."
fi

# 5. 파생물 재생성 + 검사
( cd "$HOST" && CLAUDE_PROJECT_DIR="$HOST" "$PY" .ai-harness/scripts/generate_codex_derivatives.py >/dev/null )
( cd "$HOST" && CLAUDE_PROJECT_DIR="$HOST" "$PY" .ai-harness/scripts/generate_codex_derivatives.py --check >/dev/null ) \
  && say "✓ 파생물 재생성·검사 통과" || say "[WARN] 파생물 검사 실패 — 확인 필요"

say ""
say "Post-transplant 체크리스트:"
say "  [1] .ai-harness/tdd-matrix.md 를 host 코드경로에 맞게 튜닝"
say "  [2] .ai-harness/deny-list.json 검토"
say "  [3] CLAUDE.md(host) 프로젝트 설명 확인/채움"
say "  [4] host 언어 도구(test/lint/format)의 ignore에 .ai-harness/ 추가 권장(비-git 도구는 .git/info/exclude를 안 봄)"
