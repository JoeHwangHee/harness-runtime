#!/usr/bin/env python3
"""Cold-path harness benchmark runner."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import parallelism


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BASELINE_PATH = os.path.join(ROOT, ".ai-harness", "scripts", "bench", "baseline.json")
PARALLEL_SCENARIO_PLAN = os.path.join(
    ROOT, "tests", "fixtures", "bench", "parallel-scenario", "plan.md"
)
NO_BASELINE_MESSAGE = "no baseline \u2014 run with --update-baseline"

E2E_SUITES = [
    os.path.join("tests", "e2e", "run_e2e.sh"),
    os.path.join("tests", "e2e", "run_tier01_e2e.sh"),
    os.path.join("tests", "e2e", "run_dualcli_e2e.sh"),
]

METRIC_ORDER = [
    "e2e_suites_pass",
    "e2e_assertions",
    "provenance_rate",
    "unfireable_block_rate",
    "stale_detection_works",
    "parallelism_ratio",
    "parallelism_max_width",
]

DERIVATIVE_CHECK_FILES = [
    os.path.join(".ai-harness", "harness-contract.md"),
    "CLAUDE.md",
    "AGENTS.md",
    os.path.join(".claude", "settings.json"),
    os.path.join(".codex", "config.toml"),
    os.path.join(".codex", "hooks.json"),
    os.path.join(".codex", "README.md"),
    os.path.join(".ai-harness", "scripts", "generate_codex_derivatives.py"),
    os.path.join(".ai-harness", "scripts", "harness_hash.py"),
]

EPSILON = 0.000000000001


def python_executable():
    return sys.executable or "python3"


def bench_env(extra=None):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env


def run_process(args, cwd=ROOT, extra_env=None):
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            env=bench_env(extra_env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except OSError as exc:
        return CompletedFailure(str(exc))


class CompletedFailure:
    def __init__(self, message):
        self.returncode = 127
        self.stdout = ""
        self.stderr = message


def count_pass_lines(output):
    count = 0
    for line in output.splitlines():
        if line.startswith("PASS "):
            count += 1
    return count


def measure_e2e():
    all_passed = True
    assertions = 0

    for rel_path in E2E_SUITES:
        suite_path = os.path.join(ROOT, rel_path)
        proc = run_process(["bash", suite_path])
        if proc.returncode != 0:
            all_passed = False
        assertions += count_pass_lines((proc.stdout or "") + "\n" + (proc.stderr or ""))

    return all_passed, assertions


def copy_file_to_temp(rel_path, temp_root):
    src = os.path.join(ROOT, rel_path)
    dst = os.path.join(temp_root, rel_path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def enforce_contains_hook(enforce):
    if not isinstance(enforce, str):
        return False
    return "hook" in set(part.strip() for part in enforce.split("+"))


def measure_rules_rates():
    temp_root = tempfile.mkdtemp(prefix="bench-rules-")
    try:
        src_plan = os.path.join(ROOT, "tests", "fixtures", "points", ".plan")
        plan_dir = os.path.join(temp_root, ".plan")
        shutil.copytree(src_plan, plan_dir)

        generated_rules = os.path.join(plan_dir, "rules.json")
        if os.path.exists(generated_rules):
            os.remove(generated_rules)

        proc = run_process(
            [
                python_executable(),
                os.path.join(ROOT, ".ai-harness", "scripts", "generate_rules.py"),
                "--plan-dir",
                plan_dir,
            ]
        )
        if proc.returncode != 0:
            return 0.0, 1.0

        with open(generated_rules, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        rules = payload.get("rules")
        if not isinstance(rules, list) or not rules:
            return 0.0, 1.0

        provenance_count = 0
        hook_count = 0
        unfireable_count = 0

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if rule.get("source") and rule.get("plan_step"):
                provenance_count += 1
            if enforce_contains_hook(rule.get("enforce")):
                hook_count += 1
                if not rule.get("detect") and not rule.get("path_glob"):
                    unfireable_count += 1

        provenance_rate = float(provenance_count) / float(len(rules))
        if hook_count == 0:
            unfireable_block_rate = 0.0
        else:
            unfireable_block_rate = float(unfireable_count) / float(hook_count)

        return provenance_rate, unfireable_block_rate
    except (OSError, json.JSONDecodeError, ValueError):
        return 0.0, 1.0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def measure_stale_detection():
    temp_root = tempfile.mkdtemp(prefix="bench-stale-")
    try:
        for rel_path in DERIVATIVE_CHECK_FILES:
            copy_file_to_temp(rel_path, temp_root)

        script = os.path.join(temp_root, ".ai-harness", "scripts", "generate_codex_derivatives.py")
        env = {"CLAUDE_PROJECT_DIR": temp_root}

        clean = run_process(
            [python_executable(), script, "--check"],
            cwd=temp_root,
            extra_env=env,
        )

        with open(os.path.join(temp_root, ".ai-harness", "harness-contract.md"), "a", encoding="utf-8") as handle:
            handle.write("\n# bench stale probe\n")

        stale = run_process(
            [python_executable(), script, "--check"],
            cwd=temp_root,
            extra_env=env,
        )

        return clean.returncode == 0 and stale.returncode == 3
    except OSError:
        return False
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def measure_parallelism():
    try:
        with open(PARALLEL_SCENARIO_PLAN, "r", encoding="utf-8") as handle:
            steps = parallelism.parse_plan_steps(handle.read())
        result = parallelism.analyze_parallelism(steps)
        return float(result["parallelism_ratio"]), int(result["max_wave_width"])
    except (OSError, ValueError) as exc:
        print("warning: parallelism measurement failed: %s" % exc, file=sys.stderr)
        return 0.0, 0


def measure():
    e2e_suites_pass, e2e_assertions = measure_e2e()
    provenance_rate, unfireable_block_rate = measure_rules_rates()
    stale_detection_works = measure_stale_detection()
    parallelism_ratio, parallelism_max_width = measure_parallelism()

    return {
        "e2e_suites_pass": bool(e2e_suites_pass),
        "e2e_assertions": int(e2e_assertions),
        "provenance_rate": float(provenance_rate),
        "unfireable_block_rate": float(unfireable_block_rate),
        "stale_detection_works": bool(stale_detection_works),
        "parallelism_ratio": float(parallelism_ratio),
        "parallelism_max_width": int(parallelism_max_width),
    }


def write_baseline(metrics):
    with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_baseline():
    if not os.path.exists(BASELINE_PATH):
        return None

    with open(BASELINE_PATH, "r", encoding="utf-8") as handle:
        baseline = json.load(handle)

    if not isinstance(baseline, dict):
        raise ValueError("baseline.json must contain a JSON object")
    for name in METRIC_ORDER:
        if name not in baseline:
            raise ValueError("baseline.json is missing %s" % name)
    return baseline


def is_regression(name, current, baseline):
    current_value = current[name]
    baseline_value = baseline[name]

    if name == "e2e_suites_pass":
        return baseline_value is True and current_value is False
    if name == "e2e_assertions":
        return current_value < baseline_value
    if name == "provenance_rate":
        return current_value + EPSILON < baseline_value
    if name == "unfireable_block_rate":
        return current_value > baseline_value + EPSILON
    if name == "stale_detection_works":
        return current_value is False
    # characterization (drift-pinned) axes: any deviation from baseline = flag.
    # unlike the directional quality axes above, neither direction is intrinsically
    # "worse" — these pin a structural measurement and catch silent fixture/logic drift.
    if name == "parallelism_ratio":
        return abs(current_value - baseline_value) > EPSILON
    if name == "parallelism_max_width":
        return current_value != baseline_value
    raise KeyError(name)


def json_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def print_comparison_report(current, baseline):
    any_regression = False
    for name in METRIC_ORDER:
        regression = is_regression(name, current, baseline)
        if regression:
            any_regression = True
        status = "REGRESSION" if regression else "OK"
        print(
            "[%s] %s current=%s baseline=%s"
            % (status, name, json_value(current[name]), json_value(baseline[name]))
        )
    return any_regression


def print_no_baseline_report(current):
    for name in METRIC_ORDER:
        print("%s current=%s" % (name, json_value(current[name])))
    print(NO_BASELINE_MESSAGE)


def print_json(metrics):
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="write current measurements to scripts/bench/baseline.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print current measurements as JSON",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    metrics = measure()

    if args.update_baseline:
        write_baseline(metrics)
        if args.json:
            print_json(metrics)
            print("baseline updated (human-approved)", file=sys.stderr)
        else:
            print("baseline updated (human-approved)")
        return 0

    try:
        baseline = load_baseline()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print("failed to read baseline: %s" % exc, file=sys.stderr)
        return 1

    if baseline is None:
        if args.json:
            print_json(metrics)
            print(NO_BASELINE_MESSAGE, file=sys.stderr)
        else:
            print_no_baseline_report(metrics)
        return 0

    if args.json:
        print_json(metrics)
        regression = any(is_regression(name, metrics, baseline) for name in METRIC_ORDER)
    else:
        regression = print_comparison_report(metrics, baseline)

    return 5 if regression else 0


if __name__ == "__main__":
    raise SystemExit(main())
