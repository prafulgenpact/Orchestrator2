#!/usr/bin/env python3
"""make doctor — one-command diagnosis of the whole harness.

Checks environment, toolchain (vs pinned versions), hooks, agent config,
contract state. OK / WARN / FAIL per item; exits 1 only on FAIL.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprint import repo_root  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []  # (status, item, detail)


def add(status: str, item: str, detail: str = "") -> None:
    RESULTS.append((status, item, detail))


def out(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (r.stdout or r.stderr).strip()
    except Exception:
        return ""


def rc(cmd: list[str]) -> int:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=60).returncode
    except Exception:
        return 127


def pinned_versions(root: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    f = root / "requirements-dev.txt"
    if f.exists():
        for line in f.read_text().splitlines():
            m = re.match(r"^([A-Za-z0-9._-]+)==([^\s#]+)", line.strip())
            if m:
                pins[m.group(1).lower()] = m.group(2)
    return pins


def main() -> int:
    try:
        root = repo_root()
    except Exception:
        print("FAIL not a git repository — run 'git init' (or python3 init.py) first")
        return 1

    # --- environment -----------------------------------------------------
    py = sys.version_info
    add("OK" if py >= (3, 10) else "FAIL", "python >= 3.10", f"found {py.major}.{py.minor}.{py.micro}")
    gitv = out(["git", "--version"])
    m = re.search(r"(\d+)\.(\d+)", gitv)
    git_ok = bool(m) and (int(m.group(1)), int(m.group(2))) >= (2, 9)
    add("OK" if git_ok else "FAIL", "git >= 2.9 (core.hooksPath)", gitv)

    # --- git hooks / identity --------------------------------------------
    hooks_path = out(["git", "config", "core.hooksPath"])
    add(
        "OK" if hooks_path == "githooks" else "FAIL",
        "enforcement hooks active",
        f"core.hooksPath={hooks_path or '(unset)'} — fix: bash scripts/install_hooks.sh",
    )
    for h in ("pre-commit", "pre-push", "commit-msg"):
        f = root / "githooks" / h
        ok = f.exists() and (f.stat().st_mode & 0o111)
        add("OK" if ok else "FAIL", f"githooks/{h} present+executable", "" if ok else "fix: bash scripts/install_hooks.sh")
    ident = out(["git", "config", "user.email"])
    add("OK" if ident else "WARN", "git identity", ident or "unset — commits will fail; git config user.email ...")

    # --- toolchain vs pins -------------------------------------------------
    cfg_text = (root / "verify.config").read_text() if (root / "verify.config").exists() else ""
    req_m = re.search(r'(?m)^REQUIRED_CHECKS="([^"]*)"', cfg_text)
    required = set((req_m.group(1) if req_m else "").split())
    pins = pinned_versions(root)
    tool_map = {"ruff": {"py-lint", "py-format"}, "mypy": {"py-types"}, "pytest": {"py-unit", "e2e"}}
    for tool, checks in tool_map.items():
        path = shutil.which(tool)
        needed = bool(required & checks)
        if not path:
            add("FAIL" if needed else "WARN", f"{tool} installed",
                f"missing{' and required by verify.config' if needed else ''} — fix: make bootstrap")
            continue
        ver = out([tool, "--version"])
        pin = pins.get(tool, "")
        if pin and pin not in ver:
            add("WARN", f"{tool} version matches pin", f"installed '{ver}' vs pinned {pin} (determinism drift)")
        else:
            add("OK", f"{tool} installed", ver)
    for opt in ("pip-audit", "diff-cover", "gitleaks"):
        add("OK" if shutil.which(opt) else "WARN", f"{opt} (optional lane)",
            "" if shutil.which(opt) else "not installed — lane will skip")

    # --- agent layer -------------------------------------------------------
    settings = root / ".claude" / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text())
            add("OK", ".claude/settings.json valid JSON", f"{sum(len(v) for v in data.get('hooks', {}).values())} hook groups")
            referenced = re.findall(r"scripts/[a-z_]+\.(?:sh|py)", settings.read_text())
            missing = [s for s in set(referenced) if not (root / s).exists()]
            add("OK" if not missing else "FAIL", "hook scripts referenced exist", ", ".join(missing) or "all present")
        except json.JSONDecodeError as e:
            add("FAIL", ".claude/settings.json valid JSON", str(e))
    else:
        add("WARN", ".claude/settings.json present", "agent-layer hooks inactive (git hooks + CI still enforce)")
    add("OK" if (root / ".claude" / "agents" / "auditor.md").exists() else "WARN", "auditor subagent", "")

    # --- contract state ----------------------------------------------------
    ok_cfg = rc(["bash", "-c", f'. "{root}/verify.config" && true']) == 0
    add("OK" if ok_cfg else "FAIL", "verify.config parses", "" if ok_cfg else "shell syntax error")
    obj = root / "specs" / "00-objective.md"
    if obj.exists():
        placeholder = "AC-1: …" in obj.read_text() or "TODO" in obj.read_text()[:600]
        add("OK" if not placeholder else "WARN", "objective written", "" if not placeholder else "still template/TODO — run python3 init.py or edit it")
    else:
        add("FAIL", "objective written", "specs/00-objective.md missing")
    proof_rc = rc(["python3", str(root / "scripts" / "check_proof.py"), "--quiet"])
    add("OK" if proof_rc == 0 else "WARN", "current code has a valid PASS proof",
        "" if proof_rc == 0 else "run: make verify")
    loop_rc = rc(["python3", str(root / "scripts" / "loop_detector.py")])
    add("OK" if loop_rc == 0 else "FAIL", "no active doom loop", "" if loop_rc == 0 else "see make status")
    add("OK" if out(["git", "remote"]) else "WARN", "git remote configured", "push gate untested until a remote exists")
    add("OK" if (root / ".github" / "workflows" / "verify.yml").exists() else "WARN", "CI workflow present", "")
    if (root / "web" / "package.json").exists():
        add("OK" if shutil.which("node") else "FAIL", "node available for web lane", "")

    # --- report ------------------------------------------------------------
    icons = {"OK": "✅", "WARN": "⚠️ ", "FAIL": "❌"}
    for status, item, detail in RESULTS:
        line = f"{icons[status]} {status:<4} {item}"
        if detail:
            line += f"  — {detail}"
        print(line)
    fails = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    warns = sum(1 for s, _, _ in RESULTS if s == "WARN")
    print(f"\n[doctor] {len(RESULTS)} checks: {fails} FAIL, {warns} WARN")
    if fails:
        print("[doctor] fix the FAILs before trusting the contract.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
