---
name: transplant
description: 동작 중인 하네스를 기존(brownfield) 프로젝트에 이식한다. host의 CLAUDE.md·VCS·settings.json을 보존하면서 Tier0/1/2 강제를 활성화. "하네스 이식", "기존 프로젝트에 하네스 얹기", "transplant" 류 요청에 사용. greenfield(빈 새 레포)에는 setup.sh를 쓴다.
---

# transplant — 기존 프로젝트 이식

## 절차

1. **대상 확인** — host 프로젝트 루트 경로(인자 또는 cwd)를 사용자와 확인한다. 잘못된 경로면 멈춘다.
2. **결정적 이식 실행**:
   ```bash
   bash .ai-harness/transplant.sh <host>
   ```
   (이 레포 루트에서, `<host>`는 대상 프로젝트 루트.)
3. **스터브 감지** — 출력에 `HARNESS_TRANSPLANT_STUB_CREATED=1`이 있으면 host에 프로젝트 CLAUDE.md가 없어 스터브만 생성된 것이다. 사용자에게 제안:
   > "프로젝트 CLAUDE.md가 비어 있어요. `init`으로 코드베이스를 분석해 채울까요?"
   - 승인 → `init` 스킬을 host에서 실행해 프로젝트 CLAUDE.md를 생성한다. **init이 CLAUDE.md를 다시 쓰므로 import 마커 블록을 재주입**한다:
     ```bash
     python3 .ai-harness/scripts/transplant_lib.py inject-import <host>/CLAUDE.md
     ```
   - 거부 → 스터브를 그대로 둔다.
4. **체크리스트 안내** — `.ai-harness/tdd-matrix.md`를 host 코드경로에 맞게 튜닝, `deny-list.json` 검토, `claude .`/`codex` 실행을 안내한다.

## 경계
- greenfield(빈 새 레포)는 `transplant`가 아니라 `setup.sh`. 이 스킬은 *기존 자산이 있는* 프로젝트 전용.
- svn host는 로컬 전용 ignore가 구조적으로 어렵다(스크립트가 경고로 안내) — 사용자에게 한계를 명확히 전한다.

## 격리 — 하네스 인프라 경로는 프로젝트가 아니다

**하네스 경로는 인프라**(`.ai-harness/`·`.claude/`·`.codex/`·`AGENTS.md`)이지 프로젝트 내용이 아니다. `init`으로 CLAUDE.md를 생성하거나 host 프로젝트를 파악·수정할 때 이 경로들을 프로젝트 코드로 서술·분석하지 말 것. (Claude의 Grep/Glob은 `.git/info/exclude` 덕에 이미 skip하나, init 서술 시 명시적으로 제외.)
