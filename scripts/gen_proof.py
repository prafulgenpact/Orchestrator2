#!/usr/bin/env python3
"""Assemble a tamper-evident proof-of-verification from reports/.

The proof is the contract artifact between human and agent: it binds green check
results to an exact code fingerprint. It is only ever written by this script,
as the last step of scripts/verify.sh. check_proof.py refuses anything that
does not match. FAIL proofs are recorded too — the doom-loop detector needs them.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprint import fingerprint, repo_root  # noqa: E402

SCHEMA = "proof/v1"
HISTORY_KEEP = 100


def git(args: list[str], default: str = "") -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return default


def tool_version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        text = (out.stdout or out.stderr).strip()
        return text.splitlines()[0] if text else "unknown"
    except Exception:
        return "not installed"


def parse_junit(path: Path) -> dict | None:
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    agg = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time_s": 0.0}
    for s in suites:
        agg["tests"] += int(s.get("tests", 0) or 0)
        agg["failures"] += int(s.get("failures", 0) or 0)
        agg["errors"] += int(s.get("errors", 0) or 0)
        agg["skipped"] += int(s.get("skipped", 0) or 0)
        agg["time_s"] += float(s.get("time", 0) or 0)
    agg["time_s"] = round(agg["time_s"], 2)
    return agg


def parse_coverage(path: Path) -> float | None:
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    return round(float(root.get("line-rate", 0)) * 100, 2)


def canonical_hash(obj: dict) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    root = repo_root()
    reports = root / "reports"

    checks: list[dict] = []
    jl = reports / "checks.jsonl"
    if jl.exists():
        checks = [json.loads(line) for line in jl.read_text().splitlines() if line.strip()]

    required = [c for c in os.environ.get("REQUIRED_CHECKS", "").split() if c]
    by_name = {c["name"]: c for c in checks}
    missing = [r for r in required if r not in by_name or by_name[r]["status"] == "skip"]
    failed = [c["name"] for c in checks if c["status"] == "fail"]
    result = "PASS" if checks and not failed and not missing else "FAIL"
    dirty = bool(git(["status", "--porcelain", "--untracked-files=no"]))

    proof = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result": result,
        "failed_checks": failed,
        "missing_required_checks": missing,
        "required_checks": required,
        "fingerprint": fingerprint(),
        "git": {
            "commit": git(["rev-parse", "HEAD"], "none"),
            "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], "none"),
            "dirty_tracked_files": dirty,
        },
        "checks": checks,
        "tests": {
            "unit": parse_junit(reports / "junit-unit.xml"),
            "e2e": parse_junit(reports / "junit-e2e.xml"),
            "web_e2e": parse_junit(reports / "junit-web-e2e.xml"),
            "coverage_pct": parse_coverage(reports / "coverage.xml"),
        },
        "environment": {
            "python": tool_version(["python3", "--version"]),
            "node": tool_version(["node", "--version"]),
            "ruff": tool_version(["ruff", "--version"]),
            "pytest": tool_version(["pytest", "--version"]),
            "os": tool_version(["uname", "-sr"]),
        },
    }
    proof["content_hash"] = canonical_hash(proof)

    pdir = root / "proofs"
    hdir = pdir / "history"
    hdir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(proof, indent=2) + "\n"
    (pdir / "latest.json").write_text(text)
    # microsecond stamp: multiple runs in the same second must NOT collide,
    # or the doom-loop detector undercounts the failure streak
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    (hdir / f"{stamp}-{result}.json").write_text(text)
    for old in sorted(hdir.glob("*.json"))[:-HISTORY_KEEP]:
        old.unlink()

    print(f"[proof] {result}  fingerprint={proof['fingerprint'][:12]}  -> proofs/latest.json")
    if failed:
        print(f"[proof] failed checks: {', '.join(failed)}")
    if missing:
        print(f"[proof] required checks missing/skipped: {', '.join(missing)}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
