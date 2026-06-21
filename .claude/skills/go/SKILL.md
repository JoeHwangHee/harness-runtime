---
name: go
description: 통과 플랜+규칙을 사용자 승인 후 Tier 강제하 빌드 실행
---

# Go

`go`는 스크립트가 아니라 MAIN(열린 CLI)이 따라야 하는 실행 절차다. 실제 강제는 훅과
`contract_writer.py`가 수행하고, 판정은 executor와 독립된 콜드 리뷰어가 수행한다.

## 0. 전제 검증

둘 다 충족하지 않으면 즉시 중단하고 rules-gen/리뷰 단계로 되돌린다.

1. 마커 2종이 존재해야 한다: `.plan/review-pass.json`, `.plan/rules-pass.json`.
2. 전 노드 해시 체인이 통과해야 한다.

```bash
python3 .ai-harness/scripts/check_chain.py --plan-dir .plan
```

`check_chain.py --plan-dir`가 exit 0이면 계속한다. exit 4(`chain broken at Lx`)이면 해당 단계부터
재실행하라고 안내하고 중단한다: L1=조건/brief, L2=plan/brief, L3=rules, L4=rules-pass.

## 1. 제시 + 사용자 승인

MAIN이 `.plan/rules.json`을 요약해 사용자에게 직접 제시한다.

- `scope.allow_globs`
- 규칙 수
- `enforce`별 분포: `hook`, `verification`, `reviewer`
- `verification.commands`

MAIN이 사용자에게 직접 승인을 받아야 하며, 서브에이전트에게 위임하지 않는다. 거부되면 중단한다.

## 2. 실행 개시

상태류 파일은 반드시 `contract_writer.py`로만 변경한다.

```bash
RULES_HASH=$(python3 .ai-harness/scripts/harness_hash.py file .plan/rules.json)
python3 .ai-harness/scripts/contract_writer.py init-run --plan-dir .plan --run-id <RUN_ID> --contract-root <절대 .plan 경로> --worktree-root <worktree> --rules-hash "$RULES_HASH" [--ttl 3600]
python3 .ai-harness/scripts/contract_writer.py seed-ledger --plan-dir .plan --run-id <RUN_ID>
```

`contract_writer.py init-run`은 active-run을 `running`으로 만든다. `seed-ledger`는 rules의
`requires_test`를 test-ledger에 `declared`로 등록해 편집 deadlock을 해소한다.

이 시점부터 freeze가 발동한다. 앵커류는 read-only이고, 상태류는 `contract_writer.py`만 쓸 수 있다.
훅은 raw 편집과 Bash 리다이렉트를 차단한다.

## 3. 빌드

단계별 구현은 worktree에서 executor가 수행한다. 훅은 scope 밖 편집과 detect 위반을 실시간 차단하며
위반 시 exit 2를 반환한다.

gotcha의 `requires_test`마다 executor는 TDD로 테스트를 작성한 뒤 테스트를 실제 재실행해야 한다.
exit 0인 경우에만 다음 명령으로 satisfied 처리한다.

```bash
python3 .ai-harness/scripts/contract_writer.py mark-satisfied --plan-dir .plan --rule-id <ID> --test-glob <glob> --test-cmd "<검증명령>"
```

executor는 satisfied를 직접 쓸 수 없다. 훅이 raw 편집을 차단하고, writer가 증거를 재계산한다.

## 4. 리뷰

`enforce`에 `reviewer`가 든 규칙과 최종 diff를 콜드 독립 리뷰어에 디스패치한다. 리뷰어는 executor와
독립이어야 한다.

리뷰어 산출물은 JSON이며 다음 형식이다.

```json
{ "reviewer_session_id": "...", "reviewer_checks": [{ "rule_id": "...", "verdict": "...", "evidence": "..." }], "final_diff_verdict": "pass" }
```

그 산출물과 현재 diff를 기록한다.

```bash
python3 .ai-harness/scripts/contract_writer.py review-record --plan-dir .plan --run-id <RUN_ID> --lane go --reviewer-output <리뷰어 산출 JSON> --diff-file <현재 diff>
```

`review-record --lane go`는 final-review-pass를 기록한다. verdict는 리뷰어 산출에서 도출되고
`reviewer_output_hash`와 `diff_hash`에 바인딩된다. executor 레인의 `review-record`는 거부된다.

## 5. 완료 게이트

완료는 다음 명령 하나로만 시도한다.

```bash
python3 .ai-harness/scripts/contract_writer.py run-state --plan-dir .plan --run-id <RUN_ID> --status done --diff-file <현재 diff>
```

`run-state --plan-dir .plan --run-id`는 `--status done`에서 5조건을 모두 검사한다.

1. `test-ledger`의 모든 `required_tests`가 `satisfied`다.
2. `test-ledger`에 `declared`가 남아 있지 않다.
3. `final-review-pass`의 `verdict`가 `"pass"`다.
4. 신선도: `diff_hash`가 현재 diff와 일치한다.
5. 신선도: `rules_hash`가 현재 `.plan/rules.json`과 일치한다.

통과하면 active-run은 `done`이 되고 freeze가 해제된다. 하나라도 미충족이면
`cannot mark done: <reason>`으로 거부되며 빌드를 계속한다.

### 5-1. 핫패스 텔레메트리 적재 (측정 — 자기수정 아님)

`done`이 성립하면 그 run의 텔레메트리를 passive 적재한다. **이것은 측정일 뿐 최적화가 아니다 — 하네스는 자기 프롬프트·규제·훅·계약을 고치지 않는다.** 최적화(설계 변경)는 콜드패스 `.ai-harness/scripts/bench/run_bench.py` + 사람 승인의 몫이다(핫/콜드패스 분리).

```bash
python3 .ai-harness/scripts/bench/record_run.py --plan-dir .plan --run-id <RUN_ID>
```

`.plan/bench/runs/<RUN_ID>.json`에 게이트 결과·ledger·규칙 enforce 분포·효과축(provenance·발화불가 block율·reviewer pass율)을 적재한다. 토큰·턴은 MAIN이 쥐고 있어 적재되지 않는다(harness-level). 실패해도 빌드를 막지 않는다(passive).

## 6. 복구 / 중단

중단은 항상 허용되며 freeze를 해제한다.

```bash
python3 .ai-harness/scripts/contract_writer.py run-state --plan-dir .plan --run-id <RUN_ID> --status aborted
```

TTL(`active-run.ttl`)이 지난 stale run이 있으면 다음 `go`는 경고하고 abort/recover를 안내한다.

## 현재 골격 범위

Tier 0/1(파괴적 셸·프로젝트 TDD 정책) 이식과 듀얼 CLI는 Phase 2~3 범위다. 이 `go`는
Tier 2(플랜 스코프·계약) 완전 강제와 5조건 완료 게이트를 담당한다.
