# 통합 의도→강제 하네스 (클론형 템플릿)

검증된 의도를 강제 규칙으로 컴파일하고, 그 규칙 아래 빌드를 실행하는 하네스. **의도 포착(elicitation)** 과 **규칙 강제(enforcement)** 를 한 파이프라인으로 잇는다. Claude Code · Codex 듀얼 CLI.

## 빠른 시작

```bash
git clone <this-repo> my-project && cd my-project
./setup.sh            # 멱등 — 훅 실행권한·원장 시드·Codex 파생물 재생성
claude .              # 또는  codex
```

## 무엇을 하나

```
사용자 "X 만들어줘"
  ① .plan/plan.md 초안           ② goal-interview (조건 4파일)
  ③ review-brief (콜드·plan-blind) ④ plan-review (콜드 리뷰어) → review-pass
  ⑤ rules-gen → .plan/rules.json (5중 규제) → rules-pass
  ⑥ go → Tier0/1/2 강제하 빌드 → 5조건 완료 게이트
```

운영 계약 전문은 **`.ai-harness/harness-contract.md`(SoT)** — `CLAUDE.md`는 이를 `@import`하는 얇은 메모. 설계는 `docs/harness-design.md`, 계약 스키마는 `docs/contracts.md`, 사용법은 `docs/harness-usage.md`.

## 3계층 강제

| 계층 | 무엇 | 출처 | 훅 |
|---|---|---|---|
| Tier 0 | 파국 셸·보호 경로 (always-on) | `.ai-harness/deny-list.json` | `pre_tool_use.py` |
| Tier 1 | 코드경로 TDD 원장 + 커밋 전 검증 | `.ai-harness/tdd-matrix.md`·`.ai-harness/tasks/tdd.json` | `tdd_guard.py`·`pre_commit_verification.py` |
| Tier 2 | 플랜 스코프 + 계약 freeze | `.plan/rules.json` | `plan_rules_guard.py` |

`.claude/settings.json`에 Tier0→1→2 체인. 같은 훅을 Codex가 `.codex/hooks.json`으로 미러한다.

## 듀얼 CLI — SoT와 생성물

- **SoT (직접 수정)**: `.ai-harness/harness-contract.md`, `.claude/skills/*`, `.claude/settings.json`
- **생성물 (손대지 말 것)**: `AGENTS.md`, `.codex/`  ← `.ai-harness/scripts/generate_codex_derivatives.sh`로 재생성
- 파생물 헤더에 SoT 해시가 박혀 stale을 검출(`--check` → 어긋나면 exit 3). `setup.sh`가 재생성·검사한다.

## 검증

```bash
bash tests/e2e/run_e2e.sh            # Tier2 + 계약 (happy path + 음성 12종)
bash tests/e2e/run_tier01_e2e.sh     # Tier0/1 + 합성 (over-block 0 포함)
python3 .ai-harness/scripts/generate_codex_derivatives.py --check   # 파생물 SoT 일치
```

## 환경

python3 stdlib만(외부 패키지 불필요), bash. 모든 계약은 JSON. Tier0는 파국 패턴 한정이라 정상 워크플로를 막지 않는다(over-block 0).
