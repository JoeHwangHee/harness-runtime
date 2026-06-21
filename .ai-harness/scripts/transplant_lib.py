#!/usr/bin/env python3
"""Transplant helpers (pure functions + CLI). python3 stdlib only."""
from __future__ import annotations
import copy

MARKER_BEGIN = "<!-- harness:begin -->"
MARKER_END = "<!-- harness:end -->"
IMPORT_LINE = "@.ai-harness/harness-contract.md"
EXCLUDE_BEGIN = "# >>> harness managed >>>"
EXCLUDE_END = "# <<< harness managed <<<"
HARNESS_IGNORE = [".ai-harness/", ".claude/", ".codex/", "AGENTS.md", ".plan/"]


def upsert_block(text: str, begin: str, end: str, inner: str) -> str:
    block = begin + "\n" + inner + "\n" + end
    if begin in text and end in text and text.index(begin) < text.index(end):
        start = text.index(begin)
        stop = text.index(end) + len(end)
        replaced = text[:start] + block + text[stop:]
        if not replaced.endswith("\n"):
            replaced += "\n"
        return replaced
    body = text.rstrip("\n")
    if body == "":
        return block + "\n"
    return body + "\n\n" + block + "\n"


def inject_import_block(text: str) -> str:
    return upsert_block(text, MARKER_BEGIN, MARKER_END, IMPORT_LINE)


def merge_settings(host: dict, harness: dict) -> dict:
    result = copy.deepcopy(host) if host else {}
    h_hooks = harness.get("hooks", {})
    r_hooks = result.setdefault("hooks", {})
    for event, matchers in h_hooks.items():
        r_list = r_hooks.setdefault(event, [])
        by_matcher = {m.get("matcher"): m for m in r_list}
        for hm in matchers:
            key = hm.get("matcher")
            existing = by_matcher.get(key)
            if existing is None:
                new_m = copy.deepcopy(hm)
                r_list.append(new_m)
                by_matcher[key] = new_m
            else:
                seen = {h.get("command") for h in existing.get("hooks", [])}
                for h in hm.get("hooks", []):
                    if h.get("command") not in seen:
                        existing.setdefault("hooks", []).append(copy.deepcopy(h))
                        seen.add(h.get("command"))
    return result


def make_stub(project_name: str) -> str:
    return (
        "# " + project_name + "\n\n"
        + "TODO: 프로젝트 설명을 채우세요 (또는 `init`으로 자동 생성).\n"
        + "<!-- 참고: .ai-harness/ .claude/ .codex/ AGENTS.md 는 하네스 인프라 경로이지 이 프로젝트의 코드가 아닙니다. -->\n\n"
        + MARKER_BEGIN + "\n" + IMPORT_LINE + "\n" + MARKER_END + "\n"
    )


def render_exclude(text: str) -> str:
    return upsert_block(text, EXCLUDE_BEGIN, EXCLUDE_END, "\n".join(HARNESS_IGNORE))


def _io(path, fn):
    import io, os
    text = ""
    if os.path.exists(path):
        with io.open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    out = fn(text)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(out)


def main(argv=None):
    import argparse, io, json, os
    p = argparse.ArgumentParser(description="transplant helpers")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inject-import"); a.add_argument("file")
    b = sub.add_parser("stub"); b.add_argument("name"); b.add_argument("file")
    c = sub.add_parser("merge-settings"); c.add_argument("host"); c.add_argument("harness")
    d = sub.add_parser("exclude"); d.add_argument("file")
    args = p.parse_args(argv)
    if args.cmd == "inject-import":
        _io(args.file, inject_import_block)
    elif args.cmd == "stub":
        with io.open(args.file, "w", encoding="utf-8") as fh:
            fh.write(make_stub(args.name))
    elif args.cmd == "merge-settings":
        host = {}
        if os.path.exists(args.host):
            with io.open(args.host, "r", encoding="utf-8") as fh:
                host = json.load(fh) or {}
        with io.open(args.harness, "r", encoding="utf-8") as fh:
            harness = json.load(fh) or {}
        merged = merge_settings(host, harness)
        os.makedirs(os.path.dirname(args.host) or ".", exist_ok=True)
        with io.open(args.host, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    elif args.cmd == "exclude":
        _io(args.file, render_exclude)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
