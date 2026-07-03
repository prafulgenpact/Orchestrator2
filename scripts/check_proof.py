#!/usr/bin/env python3
"""Validate the proof contract. Exit 0 only if ALL of:

  1. a proof exists (worktree proofs/latest.json, or committed inside --ref)
  2. its content_hash is intact (tamper check — hand-edited proofs are rejected)
  3. its result is PASS with no missing required checks
  4. its fingerprint matches the code being validated (worktree or --ref)
  5. (optional) it is younger than PROOF_MAX_AGE_HOURS

Used by: pre-push git hook (--ref <sha>), CI audit (--ref <sha>), agent Bash
gate (--ref HEAD), agent Stop gate (worktree), make seal / make status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprint import fingerprint, repo_root  # noqa: E402


def canonical_hash(obj: dict) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def load_proof(root: Path, ref: str | None) -> tuple[dict | None, str | None]:
    """Return (proof, error). With --ref, the proof must be committed in that ref."""
    if ref:
        res = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:proofs/latest.json"],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            return None, f"ref {ref} contains no committed proofs/latest.json (run: make verify && make seal)"
        raw = res.stdout
    else:
        p = root / "proofs" / "latest.json"
        if not p.exists():
            return None, "proofs/latest.json missing (run: make verify)"
        raw = p.read_text()
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"proof is not valid JSON: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default=None, help="validate a committed ref (e.g. HEAD or a sha)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument(
        "--max-age-hours",
        type=float,
        default=float(os.environ.get("PROOF_MAX_AGE_HOURS", "0")),
        help="0 disables the age check (fingerprint binding is the real guarantee)",
    )
    args = ap.parse_args()

    root = repo_root()
    problems: list[str] = []
    proof, err = load_proof(root, args.ref)
    if err:
        problems.append(err)

    if proof is not None:
        body = {k: v for k, v in proof.items() if k != "content_hash"}
        if canonical_hash(body) != proof.get("content_hash"):
            problems.append("TAMPERED: content_hash mismatch — the proof file was edited by hand")
        if proof.get("result") != "PASS":
            problems.append(
                f"proof result is {proof.get('result')!r} "
                f"(failed: {proof.get('failed_checks')}, missing: {proof.get('missing_required_checks')})"
            )
        want = fingerprint(args.ref)
        have = proof.get("fingerprint", "?")
        if have != want:
            where = f"ref {args.ref}" if args.ref else "worktree"
            msg = (
                f"STALE: proof fingerprint {have[:12]} != {where} fingerprint {want[:12]} — "
                "code changed after verification (run: make verify)"
            )
            if args.ref:
                parents = subprocess.run(
                    ["git", "-C", str(root), "rev-list", "--parents", "-n", "1", args.ref],
                    capture_output=True,
                    text=True,
                ).stdout.split()
                if len(parents) > 2:
                    msg += (
                        "\n    NOTE: this is a MERGE COMMIT — its combined tree was never verified. "
                        "Use squash or fast-forward merges (GitHub: allow squash merging only), "
                        "or run 'make verify' on the merged branch and push the sealed proof."
                    )
            else:
                untracked = subprocess.run(
                    ["git", "-C", str(root), "ls-files", "-o", "--exclude-standard"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                if untracked:
                    msg += (
                        "\n    NOTE: untracked files are part of the fingerprint — commit or .gitignore: "
                        + ", ".join(untracked.splitlines()[:5])
                    )
            problems.append(msg)
        if args.max_age_hours > 0 and "created_utc" in proof:
            made = datetime.fromisoformat(proof["created_utc"])
            age_h = (datetime.now(timezone.utc) - made).total_seconds() / 3600
            if age_h > args.max_age_hours:
                problems.append(f"EXPIRED: proof is {age_h:.1f}h old (max {args.max_age_hours}h)")

    ok = not problems
    if not args.quiet:
        if ok and proof is not None:
            where = f"ref {args.ref}" if args.ref else "worktree"
            print(
                f"[proof] VALID — PASS proof matches {where} "
                f"(fingerprint {proof['fingerprint'][:12]}, created {proof['created_utc']})"
            )
        else:
            print("[proof] INVALID:", file=sys.stderr)
            for m in problems:
                print(f"  - {m}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
