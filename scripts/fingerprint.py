#!/usr/bin/env python3
"""Deterministic code fingerprint — the anchor of the proof-of-testing contract.

Fingerprint = sha256 over the sorted list of (git-blob-sha, path) for every file
that counts as "code", excluding paths matched by .proofignore. A proof is valid
only for the exact fingerprint it was generated against: change one byte of code
and the proof dies.

Modes:
  (default)   worktree: tracked + untracked(non-ignored) files as they are on disk
  --ref REF   files as committed in REF (used by pre-push hook and CI audit)
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import subprocess
import sys
from pathlib import Path

DEFAULT_IGNORES = ["proofs/**", "reports/**", ".git/**"]


def sh(args: list[str], cwd: str | None = None) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, cwd=cwd).stdout


def repo_root() -> Path:
    return Path(sh(["git", "rev-parse", "--show-toplevel"]).strip())


def load_patterns(root: Path) -> list[str]:
    pats = list(DEFAULT_IGNORES)
    f = root / ".proofignore"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line)
    return pats


def is_ignored(path: str, pats: list[str]) -> bool:
    """Match full path, directory prefix (pat/ or pat/**), or basename glob (*.md)."""
    name = path.rsplit("/", 1)[-1]
    for pat in pats:
        if pat.endswith("/**") or pat.endswith("/"):
            prefix = pat[:-3] if pat.endswith("/**") else pat[:-1]
            prefix = prefix.rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False


def entries_worktree(root: Path) -> list[tuple[str, str]]:
    out = sh(["git", "-C", str(root), "ls-files", "-c", "-o", "--exclude-standard"])
    files = sorted({p for p in out.splitlines() if p})
    existing = [p for p in files if (root / p).is_file()]
    shas: list[str] = []
    if existing:
        res = subprocess.run(
            ["git", "-C", str(root), "hash-object", "--stdin-paths"],
            input="\n".join(existing) + "\n",
            capture_output=True,
            text=True,
            check=True,
        )
        shas = res.stdout.splitlines()
    sha_map = dict(zip(existing, shas))
    return [(sha_map.get(p, "MISSING"), p) for p in files]


def entries_ref(root: Path, ref: str) -> list[tuple[str, str]]:
    out = sh(["git", "-C", str(root), "ls-tree", "-r", ref])
    entries: list[tuple[str, str]] = []
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            entries.append((parts[2], path))
    return entries


def fingerprint(ref: str | None = None) -> str:
    root = repo_root()
    pats = load_patterns(root)
    entries = entries_ref(root, ref) if ref else entries_worktree(root)
    kept = sorted((sha, p) for sha, p in entries if not is_ignored(p, pats))
    payload = "\n".join(f"{sha} {p}" for sha, p in kept)
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default=None, help="fingerprint a committed ref instead of the worktree")
    args = ap.parse_args()
    print(fingerprint(args.ref))
    return 0


if __name__ == "__main__":
    sys.exit(main())
