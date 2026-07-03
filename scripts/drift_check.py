#!/usr/bin/env python3
"""Scope-drift detector: changed files must match the ACTIVE task's declared scope.

Independent of the agent's self-reporting. Reads the 'Scope:' globs and 'Type:'
from specs/tasks/ACTIVE.md and compares them with every file changed vs the base
branch (committed + uncommitted + untracked).

Also enforces the anti-doom-loop rule for bugfix tasks: a fix that touches source
but adds/changes no test is not a fix — it is an unverified claim.

Exit codes: 0 ok (or warning mode), 1 drift with STRICT_SCOPE=1.
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprint import repo_root  # noqa: E402

# Meta files never count as drift: plans, docs, state, and generated evidence.
ALWAYS_ALLOWED = [
    "specs/**",
    "docs/**",
    "proofs/**",
    "reports/**",
    "STATE.md",
    "CHANGELOG.md",
    "README.md",
]


def git_lines(args: list[str]) -> list[str]:
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    return [line for line in res.stdout.splitlines() if line.strip()]


def task_scope(task: Path) -> tuple[list[str] | None, str | None]:
    if not task.exists():
        return None, None
    text = task.read_text()
    scope = re.search(r"^Scope:\s*(.+)$", text, re.M)
    ttype = re.search(r"^Type:\s*(\w+)", text, re.M)
    globs = [g.strip() for g in scope.group(1).split(",") if g.strip()] if scope else None
    return globs, ttype.group(1).lower() if ttype else None


def matches(path: str, globs: list[str]) -> bool:
    for pat in globs:
        if pat.endswith("/**") or pat.endswith("/"):
            prefix = (pat[:-3] if pat.endswith("/**") else pat[:-1]).rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif fnmatch.fnmatch(path, pat):
            return True
    return False


def changed_files(base: str) -> list[str]:
    merge_base = ""
    res = subprocess.run(["git", "merge-base", base, "HEAD"], capture_output=True, text=True)
    if res.returncode == 0:
        merge_base = res.stdout.strip()
    committed = git_lines(["diff", "--name-only", f"{merge_base}..HEAD"]) if merge_base else []
    uncommitted = git_lines(["diff", "--name-only", "HEAD"])
    untracked = git_lines(["ls-files", "-o", "--exclude-standard"])
    return sorted(set(committed + uncommitted + untracked))


def main() -> int:
    root = repo_root()
    os.chdir(root)
    base = os.environ.get("BASE_BRANCH", "main")
    strict = os.environ.get("STRICT_SCOPE") == "1"

    globs, ttype = task_scope(root / "specs" / "tasks" / "ACTIVE.md")
    if globs is None:
        print("[drift] no ACTIVE task with a 'Scope:' line — scope check skipped "
              "(create one via 'make task NAME=...' for enforcement)")
        return 0

    changed = changed_files(base)
    out_of_scope = [f for f in changed if not matches(f, globs + ALWAYS_ALLOWED)]

    warnings: list[str] = []
    if ttype == "bugfix":
        src_touched = any(not f.startswith(("tests/", "specs/", "docs/", "proofs/")) for f in changed)
        tests_touched = any(f.startswith("tests/") or "/tests/" in f or ".test." in f or ".spec." in f
                            for f in changed)
        if src_touched and not tests_touched:
            warnings.append(
                "bugfix task changes source but no test was added/changed — "
                "a fix without a regression test is an unverified claim, not a fix"
            )

    if out_of_scope:
        print(f"[drift] OUT-OF-SCOPE changes (task scope: {', '.join(globs)}):", file=sys.stderr)
        for f in out_of_scope:
            print(f"  - {f}", file=sys.stderr)
    for w in warnings:
        print(f"[drift] WARNING: {w}", file=sys.stderr)

    if out_of_scope or warnings:
        print("  -> revert these, or consciously widen the task's Scope: line (human decision).",
              file=sys.stderr)
        return 1 if strict else 0

    print(f"[drift] OK — {len(changed)} changed file(s), all within scope")
    return 0


if __name__ == "__main__":
    sys.exit(main())
