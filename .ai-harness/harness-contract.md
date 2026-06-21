# 통합 의도→강제 하네스 — 운영 계약 (SoT)

**이 레포는 클론형 하네스 템플릿이다.** 목적: *검증된 의도를 강제 규칙으로 컴파일하고, 그 규칙 아래 빌드를 실행*한다. 의도 포착(elicitation)과 규칙 강제(enforcement)를 한 파이프라인으로 잇는다.

이 파일(`harness-contract.md`)은 **단일 진실원천(SoT)** 이다. `.claude/skills/*`·`.claude/agents/*`도 SoT다. `AGENTS.md`·`.codex/`·`.agents/`는 **생성물** — 손으로 고치지 말고 `.ai-harness/scripts/generate_codex_derivatives.sh`로 재생성한다(헤더에 SoT 해시가 박혀 stale을 검출).

설계 전문: `docs/harness-design.md` · 계약 스키마: `docs/contracts.md`.

## 파이프라인 (① → ⑥)

```
사용자 "X 만들어줘"
  ① .plan/plan.md 초안 (단계 · 선언 표면 · 의존성)
  ② goal-interview  — 조건 4파일 포착 (goal/spec/conventions/gotchas.md)   [skill, MAIN]
  ③ review-brief    — 조건을 앵커로 정제 (콜드 서브, plan-blind)            [skill]
  ④ plan-review     — 메인플랜을 앵커에 비추어 검수 (콜드 리뷰어)            [skill]
        ▼ 통과 → review-pass.json (plan_hash + brief_hash)
  ⑤ rules-gen       — 통과 플랜 ∩ 조건 → .plan/rules.json (5중 규제) + rules-pass.json [skill]
  ⑥ go              — 사용자 승인 → Tier0/1/2 강제하 빌드 → 5조건 완료 게이트 [skill]
```

전반부 ①~④는 의도를 *형성*하는 구간이라 강제는 게이트(④검증·⑤규제)로만. ⑥에서 코드가 써지는 순간 **Tier0+1+2가 전부 하드 차단으로 깨어난다**.

## 에이전트 토폴로지 (컨텍스트는 아티팩트로 흐른다)

- **MAIN (열린 CLI = control plane)**: ①플랜·②goal-interview(👤대화)·⑤rules-gen·⑥go 지휘. 대화·재루프·판단 맥락 보유.
- **콜드 서브(매 단계 재시작)**: ③review-brief 저작(plan-blind)·④플랜 검증·⑤규칙 검증·⑥최종 diff 검증. 스레드 기억이 아니라 `rules.json`·`review-brief.md` 등 **아티팩트를 재독**해 맥락 재구성 → 작성자와 끝까지 독립.
- **executor (Codex 레인)**: ⑥에서 격리 worktree로 구현+TDD. 자기보고 불신, 증거(exit code·diff) 기반.

## 3계층 강제 모델

| 계층 | 무엇 | 출처 | 차단 주체 |
|---|---|---|---|
| **Tier 0** 정적 안전 바닥 | 파국 셸·보호 경로 패턴 (always-on, 우회 없음) | `.ai-harness/deny-list.json` | `pre_tool_use.py` |
| **Tier 1** 프로젝트 TDD 정책 | 코드경로(`src/app/lib`) 편집 시 원장 항목 존재 + 커밋 전 검증 | `.ai-harness/tdd-matrix.md` + `.ai-harness/tasks/tdd.json` | `tdd_guard.py`, `pre_commit_verification.py` |
| **Tier 2** 플랜 스코프 | 선언 표면 밖 차단 + detect 정규식 + 실행 중 계약 freeze(=writer 권한 모델) | `.plan/rules.json` | `plan_rules_guard.py` |

훅 체인 순서: **Tier0 → Tier1 → Tier2** (`.claude/settings.json`, matcher `Edit|Write`·`Bash`). 어느 하나라도 `exit 2`면 도구 차단.

**훅을 과대평가하지 않는다**: 훅은 *구문적*(정규식·경로)만. *의미적* 강제(gotcha 안전장치·merge·런타임)는 `go` 오케스트레이션 + 검증 게이트 + 콜드 리뷰어의 몫. 그래서 "gotcha→하드게이트"는 단일 훅이 아니라 **합성**〔훅: 경로+필수테스트 존재〕+〔검증: 실행〕+〔리뷰어: 판단〕이다. 이 합성의 **첫 다리(필수테스트/훅 존재)는 컴파일 전제로 강제**된다 — `rules-gen`의 `generate_rules`가 `check_gotcha_coverage`로 `gotchas.md`의 모든 `Gn` 함정이 `requires_test`/훅 규칙으로 커버되거나 명시 waiver됐는지 검사해, 미커버면 `rules.json`을 만들지 않는다(exit 3). 그래야 함정 누락이 콜드 리뷰어 판단에만 의존하지 않는다.

## 운영 계약 — 위조 불가 상태 전이

상태류 계약(`test-ledger.json`·`final-review-pass.json`·`active-run.json`)은 **손으로 안 쓴다**. 유일한 변경 경로는 인가 writer `.ai-harness/scripts/contract_writer.py` 서브커맨드이고, 각 전이는 쓰기 전 증거/해시를 *스스로 재계산*한다(자가 채점 차단):
- `mark-satisfied` = 테스트 실제 재실행·exit 0일 때만 `declared→satisfied`.
- `review-record` = 콜드 리뷰어 산출물 출처(`reviewer_output_hash`)+diff 재해시 바인딩, **go/reviewer 레인 전용**(executor 거부).
- `run-state done` = 5조건 완료 게이트 통과 시에만.

앵커류(plan·조건4·brief·rules·두 pass 마커)는 실행 중 freeze로 read-only. 훅은 worktree 복사본이 아니라 `active-run.json.contract_root`(canonical)를 기준으로 계약을 읽는다.

## go 완료 게이트 (5조건 전부)

① ledger 전 항목 `satisfied`(파일존재+검증실행+exit0) · ② `verification.commands` 통과 · ③ 필요 시 smoke · ④ 모든 `enforce=reviewer` 규칙 `pass` · ⑤ 최종 diff `pass` **및 신선도 재해시 일치**(diff·증거·리뷰어 산출물). 하나라도 미충족이면 done 안 됨.

## Required reads (작업 전)

- `docs/harness-design.md` (설계) · `docs/contracts.md` (계약 스키마)
- 활성 작업이 있으면: `.plan/plan.md`, `.plan/rules.json`, `.plan/active-run.json`

## 벤치 — 핫/콜드패스 분리 (측정 ≠ 최적화)

*측정*과 *최적화(설계 변경)*는 다른 행위·시점·주체다. **런타임 자기수정 금지.**
- **핫패스 (매 go run · passive 측정)**: `go` done 직후 `.ai-harness/scripts/bench/record_run.py`가 계약 산출물에서 텔레메트리를 파생해 `.plan/bench/runs/<run_id>.json`에 적재. 게이트·ledger·enforce 분포·효과축(provenance·발화불가 block율·reviewer pass율). 토큰·턴은 MAIN-held라 미적재. **하네스 프롬프트·규제·훅·계약을 고치지 않는다.**
- **콜드패스 (명시 트리거 · 사람 승인)**: `.ai-harness/scripts/bench/run_bench.py`가 고정 시나리오를 실측해 `baseline.json` 대비 회귀 비교(회귀 시 exit 5). **baseline 갱신은 `--update-baseline` 플래그로만**(자동 self-modify 금지). 효과축이 baseline보다 나빠지면 회귀.
- **콜드패스 characterization(drift-pinned) 축 — 보강 #2 트리거 계측**: `.ai-harness/scripts/bench/parallelism.py`가 대표 시나리오(`tests/fixtures/bench/parallel-scenario/plan.md`)의 Step/Depends 그래프에서 `parallelism_ratio`(=serial_cost/wave_count)·`parallelism_max_width`를 도출. directional 품질축과 달리 baseline에서 **어느 방향이든** 벗어나면 회귀(픽스처/로직 silent drift 검출). **정직성 경계**: 이는 *구조적 병렬성 잠재력*(deterministic·token-free)이지 측정된 처리량이 아니다 — 콜드패스는 실제 멀티에이전트 빌드 wall-clock을 못 잰다. 보강 #2(go wave/parallel)의 착수 트리거(빌드 처리량 병목)를 **evaluable하게 만드는 계측일 뿐 빌드를 약속하지 않는다**. 현재 판독: 대표 시나리오 2.0·실제 픽스처(points) 1.0·realized(단일 레인) 1.0.

## 스킬 사용

- **`rules-gen`** — 통과 플랜 ∩ 조건 → `rules.json`. 전제 3종(plan/brief/conditions 해시 일치) 불충족 시 거부. **gotcha 커버리지 게이트**: `gotchas.md`의 각 `Gn`을 `source: gotchas.md#Gn` + `requires_test`/훅 규칙으로 커버하거나 `rules-draft.json`의 `waivers[{gotcha_id,reason}]`로 명시 면제 — 미커버·미면제·미구조 시 컴파일 거부(exit 3).
- **`go`** — 전제(두 마커 + 전 노드 해시 체인) 검사 → 👤승인 → `active-run` 기록 → ledger seed → 강제하 빌드 → 완료 게이트. 복구: `go abort`/`go recover`.
- **`transplant`** — 동작 중인 하네스를 기존 프로젝트에 이식(host CLAUDE.md·VCS·settings 보존, Tier 강제 활성화). greenfield는 `setup.sh`.
- 기존 `goal-interview`·`review-brief`·`plan-review`는 재사용(무변경).

## 환경 제약

- 스크립트는 **python3 stdlib만**(이 환경엔 `python` 없음, `python3`). bash 3.2(globstar 없음 → python `fnmatch`). 모든 계약은 JSON.
- Tier0는 *파국 패턴 한정* — 정상 워크플로(`git`·`python3`·`codex exec`·이름있는 `rm`)는 통과(over-block 0). 안전 바닥에 환경변수 우회를 두지 않는다.

## 듀얼 CLI

같은 `rules.json`·훅을 Claude Code와 Codex가 공유하되 **집행 위상이 다르다**: Claude는 PreToolUse 훅 `exit 2` hard-block 중심, Codex는 훅(guardrail)+sandbox·permissions(`.codex/config.toml`)+go 검증 게이트+final review **합성**. `.codex/hooks.json`이 `.claude/settings.json`을 Codex 지원 이벤트로 미러한다.
