#!/usr/bin/env python3
"""Secret scanner — stdlib fallback so the security lane always runs.

If you have gitleaks installed, use it too (stricter); this scanner guarantees
a baseline even on machines with nothing but python3 + git.

Scans tracked + untracked(non-ignored) files (or --staged files only) for
credential patterns. Findings fail the check — and therefore the proof.

Suppressions (deliberate, visible, reviewable):
  - line contains 'secret-ok' (inline, for docs/examples)
  - .secretsallow file: one 'pattern-name:path-glob' per line
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("generic-secret", re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|auth[_-]?token|password|passwd)\b"
        r"\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    )),
    # .env-style UNQUOTED assignments: API_KEY=sk-abc123...  (full-line, uppercase
    # var ending in a secret-ish suffix, raw value >=16 chars — catches the most
    # common real-world leak format that quoted-only patterns miss)
    ("env-secret", re.compile(
        r"^\s*(?:export\s+)?[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?)"
        r"\s*=\s*[A-Za-z0-9_\-./+]{16,}\s*$", re.M
    )),
    ("bearer-token", re.compile(r"(?i)\bauthorization\s*[:=]\s*['\"]?bearer\s+[a-z0-9._=-]{20,}")),
]

SKIP_DIRS = ("proofs/", "reports/", ".git/")
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".ico", ".woff", ".woff2", ".lock")


def git_lines(args: list[str]) -> list[str]:
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    return [line for line in res.stdout.splitlines() if line.strip()]


def load_allow(root: Path) -> list[tuple[str, str]]:
    f = root / ".secretsallow"
    entries: list[tuple[str, str]] = []
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                name, glob = line.split(":", 1)
                entries.append((name.strip(), glob.strip()))
    return entries


def allowed(name: str, path: str, allow: list[tuple[str, str]]) -> bool:
    return any(n == name and fnmatch.fnmatch(path, g) for n, g in allow)


def main() -> int:
    staged = "--staged" in sys.argv
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if res.returncode != 0:
        print("[secrets] not a git repository — nothing to scan", file=sys.stderr)
        return 1
    root = Path(res.stdout.strip())
    allow = load_allow(root)

    if staged:
        files = git_lines(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    else:
        files = git_lines(["ls-files", "-c", "-o", "--exclude-standard"])

    findings: list[str] = []
    for rel in sorted(set(files)):
        if rel.startswith(SKIP_DIRS) or rel.endswith(SKIP_SUFFIXES) or rel == ".secretsallow":
            continue
        p = root / rel
        if not p.is_file():
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:  # binary
            continue
        text = raw.decode("utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "secret-ok" in line:
                continue
            for name, pat in PATTERNS:
                if pat.search(line) and not allowed(name, rel, allow):
                    findings.append(f"{name}  {rel}:{lineno}")

    if findings:
        print("[secrets] potential credentials found — commit/verification blocked:", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        print(
            "  If a finding is a deliberate example: add inline 'secret-ok' comment,\n"
            "  or a 'pattern-name:path-glob' line to .secretsallow (reviewed like code).",
            file=sys.stderr,
        )
        return 1
    scope = "staged files" if staged else f"{len(files)} files"
    print(f"[secrets] clean ({scope})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
