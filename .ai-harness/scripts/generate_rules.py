#!/usr/bin/env python3
"""Compile .plan/rules.json from reviewed plan inputs and rules-draft.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.dont_write_bytecode = True

import harness_hash  # noqa: E402
import check_gotcha_coverage  # noqa: E402


STEP_RE = re.compile(r"^##\s+Step\s+\d+:\s+.+$")
TOUCHED_RE = re.compile(r"^Touched:\s*(.+?)\s*$")
CONDITIONS_MARKER_RE = re.compile(r"^<!--\s*conditions_hash:\s*(\S+)\s*-->$")
VALID_SOURCE_FILES = {"goal.md", "spec.md", "conventions.md", "gotchas.md"}
VALID_ENFORCE_MODES = {"hook", "verification", "reviewer"}
HOOK_DETECT_PHASES = {"command", "proposed_patch", "proposed_content"}


def parse_allow_globs(plan_text: str) -> list[str]:
    allow_globs: set[str] = set()
    in_step = False

    for line in plan_text.splitlines():
        if STEP_RE.match(line):
            in_step = True
            continue
        if line.startswith("## "):
            in_step = False

        if not in_step:
            continue

        touched = TOUCHED_RE.match(line)
        if not touched:
            continue

        for glob in touched.group(1).split(","):
            glob = glob.strip()
            if glob:
                allow_globs.add(glob)

    return sorted(allow_globs)


def fail_premise(message: str) -> int:
    print(f"broken premise: {message}", file=sys.stderr)
    return 3


def load_review_pass(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        marker = json.load(f)
    if not isinstance(marker, dict):
        raise ValueError("review-pass.json must contain a JSON object")
    return marker


def extract_brief_conditions_hash(brief_path: Path) -> str | None:
    first_line = brief_path.read_text(encoding="utf-8").splitlines()[0:1]
    if not first_line:
        return None
    match = CONDITIONS_MARKER_RE.match(first_line[0])
    if not match:
        return None
    return match.group(1)


def validate_premises(plan_dir: Path) -> tuple[str, str, str] | int:
    review_pass_path = plan_dir / "review-pass.json"
    review_brief_path = plan_dir / "review-brief.md"
    plan_path = plan_dir / "plan.md"

    if not review_pass_path.exists():
        return fail_premise(
            "review-pass.json 부재 → review-brief→plan-review→write_review_pass 재실행"
        )
    if not review_brief_path.exists():
        return fail_premise(
            "review-brief.md 부재 → review-brief→plan-review→write_review_pass 재실행"
        )
    if not plan_path.exists():
        return fail_premise("plan.md 부재 → plan 작성부터 재실행")

    try:
        review_pass = load_review_pass(review_pass_path)
        plan_hash = harness_hash.file_hash(plan_path)
        brief_hash = harness_hash.file_hash(review_brief_path)
        current_conditions_hash = harness_hash.conditions_hash(plan_dir)
        brief_conditions_hash = extract_brief_conditions_hash(review_brief_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return fail_premise(
            f"전제 파일 읽기 실패({exc}) → review-brief→plan-review→write_review_pass 재실행"
        )

    if plan_hash != review_pass.get("plan_hash"):
        return fail_premise(
            "(i) plan_hash 불일치 → plan.md가 plan-review 이후 변경됨, "
            "review-brief→plan-review→write_review_pass 재실행"
        )
    if brief_hash != review_pass.get("brief_hash"):
        return fail_premise(
            "(ii) brief_hash 불일치 → review-brief.md가 plan-review 이후 변경됨, "
            "review-brief→plan-review→write_review_pass 재실행"
        )
    if brief_conditions_hash != current_conditions_hash:
        return fail_premise(
            "(iii) conditions_hash 불일치 → 조건 파일 또는 review-brief.md가 stale, "
            "review-brief→plan-review→write_review_pass 재실행"
        )

    return plan_hash, brief_hash, current_conditions_hash


def source_filename(source: Any) -> str:
    path_part = str(source).split("#", 1)[0]
    return Path(path_part).name


def normalize_enforce(enforce: Any) -> set[str]:
    if not isinstance(enforce, str):
        return set()
    return {
        token
        for token in (part.strip() for part in enforce.split("+"))
        if token in VALID_ENFORCE_MODES
    }


def has_gotcha_matcher(rule: dict[str, Any]) -> bool:
    return bool(rule.get("path_glob")) and bool(rule.get("requires_test"))


def get_detect(rule: dict[str, Any]) -> dict[str, Any]:
    detect = rule.get("detect")
    return detect if isinstance(detect, dict) else {}


def has_hook_detect_matcher(rule: dict[str, Any]) -> bool:
    detect = get_detect(rule)
    return bool(detect.get("forbid_regex")) and detect.get("phase") in HOOK_DETECT_PHASES


def compile_rules(candidates: list[Any]) -> list[dict[str, Any]]:
    compiled: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            print("dropped: <non-object> (invalid-rule)", file=sys.stderr)
            continue

        rule = dict(candidate)
        rule_id = str(rule.get("id", "<missing-id>"))

        if not (rule.get("source") and rule.get("plan_step")):
            print(f"dropped: {rule_id} (missing-provenance)", file=sys.stderr)
            continue

        if source_filename(rule.get("source")) not in VALID_SOURCE_FILES:
            print(f"dropped: {rule_id} (off-source)", file=sys.stderr)
            continue

        modes = normalize_enforce(rule.get("enforce"))
        if "hook" in modes:
            detect = get_detect(rule)
            if detect.get("phase") == "post_write_tree":
                modes.discard("hook")
                modes.add("verification")
                rule["rerouted"] = "hook->verification"
                print(f"rerouted: {rule_id} (post_write_tree)", file=sys.stderr)
            elif has_gotcha_matcher(rule) or has_hook_detect_matcher(rule):
                pass
            else:
                modes.discard("hook")
                rule["downgraded_from"] = "hook"
                print(f"downgraded: {rule_id} (missing-matcher)", file=sys.stderr)

            if not modes:
                modes.add("reviewer")

        if "hook" not in modes:
            rule.pop("severity", None)

        rule["enforce"] = "+".join(sorted(modes))
        compiled.append(rule)

    return compiled


def load_draft(path: Path) -> tuple[list[Any], dict[str, Any], list[Any]]:
    with path.open("r", encoding="utf-8") as f:
        draft = json.load(f)

    if not isinstance(draft, dict):
        raise ValueError("rules-draft.json must contain a JSON object")

    rules = draft.get("rules")
    if not isinstance(rules, list):
        raise ValueError("rules-draft.json must contain a top-level rules array")

    verification = draft.get("verification", {"commands": []})
    if not isinstance(verification, dict):
        raise ValueError("rules-draft.json verification must be a JSON object")

    waivers = draft.get("waivers", [])
    if not isinstance(waivers, list):
        raise ValueError("rules-draft.json waivers must be a JSON array")

    return rules, verification, waivers


def write_rules(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-dir", default=".plan", help="directory containing plan artifacts")
    args = parser.parse_args()

    plan_dir = Path(args.plan_dir)
    plan_path = plan_dir / "plan.md"
    draft_path = plan_dir / "rules-draft.json"
    output_path = plan_dir / "rules.json"

    premise_result = validate_premises(plan_dir)
    if isinstance(premise_result, int):
        return premise_result
    plan_hash, brief_hash, current_conditions_hash = premise_result

    missing = [path for path in (draft_path,) if not path.exists()]
    if missing:
        for path in missing:
            print(f"missing required file: {path}", file=sys.stderr)
        return 1

    try:
        plan_text = plan_path.read_text(encoding="utf-8")
        candidates, verification, waivers = load_draft(draft_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"failed to load inputs: {exc}", file=sys.stderr)
        return 1

    compiled = compile_rules(candidates)

    # gotcha 커버리지 게이트 (waiver reason 검증 → 구조 → 미커버; stale 은 경고)
    for waiver in waivers:
        if not isinstance(waiver, dict):
            return fail_premise("(iv-c) waiver 항목이 객체가 아님")
        if not str(waiver.get("gotcha_id", "")).strip():
            return fail_premise("(iv-c) waiver gotcha_id 누락")
        if not str(waiver.get("reason", "")).strip():
            return fail_premise(
                f"(iv-c) waiver reason 누락: {waiver.get('gotcha_id')}"
            )

    gotchas_path = plan_dir / "gotchas.md"
    try:
        gotchas_text = gotchas_path.read_text(encoding="utf-8") if gotchas_path.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        return fail_premise(f"gotchas.md 읽기 실패: {exc}")

    coverage = check_gotcha_coverage.evaluate(gotchas_text, compiled, waivers)
    for stale in coverage["stale_waivers"]:
        print(f"warning: stale waiver: {stale}", file=sys.stderr)
    if coverage["structural_error"]:
        return fail_premise(
            "(iv-a) gotchas.md 에 함정 산문은 있으나 Gn ID/none-센티넬 없음 "
            "— '### Gn:' 형식 또는 '<!-- gotchas: none -->' 명시"
        )
    if coverage["uncovered"]:
        return fail_premise(
            "(iv-b) gotcha 미커버: "
            + ", ".join(coverage["uncovered"])
            + " — requires_test/훅 규칙 추가 또는 waiver"
        )

    payload = {
        "plan_hash": plan_hash,
        "brief_hash": brief_hash,
        "conditions_hash": current_conditions_hash,
        "scope": {"allow_globs": parse_allow_globs(plan_text)},
        "rules": compiled,
        "verification": verification,
        "waivers": waivers,
    }

    try:
        write_rules(output_path, payload)
    except OSError as exc:
        print(f"failed to write {output_path}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
