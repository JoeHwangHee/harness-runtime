---
name: rules-gen
description: 통과 플랜 ∩ 조건 → .plan/rules.json 규칙 생성
---

# rules-gen

## 역할

통과 플랜과 조건의 교집합만 규칙으로 만든다. 이 스킬이 `plan.md`, review brief, 조건 파일을 읽고 후보 규칙을 `.plan/rules-draft.json`으로 저작한 뒤, `python3 .ai-harness/scripts/generate_rules.py`로 `.plan/rules.json`을 결정론적으로 컴파일한다.

## 입력

- `.plan/plan.md`: `## Step N: ...`와 `Touched:` 범위를 포함한 통과 플랜.
- Review brief 또는 사용자 조건: 이번 변경에서 실제로 지켜야 할 근거.
- `conditions`, `conventions`, `gotchas`류 문서: 규칙의 출처가 되는 명시 조건.

## 후보 규칙

`.plan/rules-draft.json`은 최상위 `rules` 배열을 가진다. 각 후보 규칙은 다음 필드를 사용한다.

- `id`: 안정적인 규칙 식별자.
- `kind`: `convention`, `gotcha`, `contract` 등 규칙 성격.
- `enforce`: `hook` 또는 `reviewer`.
- `severity`: hook 차단 수준이 필요할 때만 사용.
- `detect.path_glob`: hook이 검사할 파일 glob.
- `detect.forbid_regex`: hook이 금지할 정규식.
- `reviewer_check`: reviewer가 확인할 문장.
- `path_glob` / `requires_test`: gotcha를 하드게이트할 때 — 편집 대상 경로 glob + 의무 테스트 glob. `requires_test`는 test-ledger row를 만들어 `satisfied`까지 강제한다.
- `source`: 규칙 근거 문서와 위치. gotcha 규칙은 `gotchas.md#Gn`(해당 함정 ID).
- `plan_step`: 규칙이 적용되는 플랜 단계.

## 컴파일

`.ai-harness/scripts/generate_rules.py`가 `.plan/plan.md`와 `.plan/rules-draft.json`을 읽어 `.plan/rules.json`을 쓴다. 스크립트는 `plan_hash`, `scope.allow_globs`, 통과 규칙 배열을 만든다.

스크립트가 강제하는 규제:

- (a) provenance: `source`와 `plan_step`이 둘 다 truthy인 규칙만 emit한다.
- (e) enforceability: `enforce:"hook"`은 `detect.path_glob`과 `detect.forbid_regex`가 있을 때만 유지한다. 없으면 `enforce:"reviewer"`로 강등하고 `downgraded_from:"hook"`을 붙인다.

## gotcha 커버리지 (하드게이트)

`gotchas.md`의 각 함정은 `### Gn:` 헤딩으로 안정적 ID를 갖는다(함정 없으면 `<!-- gotchas: none -->`). `generate_rules`는 모든 `Gn`이 **하드게이트로 커버**됐는지 검사한다 — 커버 = `source: "gotchas.md#Gn"`이고 `requires_test`(→ledger→satisfied) **또는** 훅(`enforce`에 `hook`)인 규칙. reviewer-only는 커버로 치지 않는다(의미적 판단일 뿐 하드게이트 아님).

이번 계획과 무관한 함정은 `rules-draft.json` 최상위 `waivers: [{"gotcha_id": "Gn", "reason": "..."}]`로 명시 면제한다(`reason` 필수, 비면 거부). **미커버·미면제거나, 함정 산문은 있는데 `Gn`/센티넬이 없으면 컴파일 거부**(exit 3) — rules.json이 안 나온다. 이로써 "각 암묵지는 하드게이트로 커버되거나 의식적으로 면제된다"가 구조적으로 보장된다.

## 규율

추측 금지(더 견고/재사용/미래대비를 근거로 한 규칙 금지). 출처 없는데 필요해 보이면 사용자에게 질의. 면제는 남발하지 말 것 — gotcha를 waiver할 땐 *정말로 이번 계획과 무관한지*를 보수적으로 판단하고 사유를 적는다.
