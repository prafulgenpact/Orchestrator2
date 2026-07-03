#!/usr/bin/env python3
"""Doom-loop detector: N consecutive FAIL proofs sharing the same failing check.

A doom loop = the agent keeps "fixing" but the same check keeps failing, or a fix
"appears" done without evidence. Because every verify run writes a proof to
proofs/history/ (PASS and FAIL alike), this detector has an objective record.

When a loop is detected, further verification is BLOCKED until a human:
  1. reviews the '## Failure analysis' the agent must write in specs/tasks/ACTIVE.md
  2. re-runs with:  make verify LOOP_ACK=1

Agents are forbidden from setting LOOP_ACK — the Bash gate (gate_bash.sh) blocks it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprint import repo_root  # noqa: E402


def main() -> int:
    threshold = int(os.environ.get("LOOP_THRESHOLD", "3"))
    hdir = repo_root() / "proofs" / "history"
    if not hdir.exists():
        return 0

    streak: list[dict] = []
    for f in sorted(hdir.glob("*.json"), reverse=True):  # newest first
        try:
            proof = json.loads(f.read_text())
        except Exception:
            continue
        if proof.get("result") == "PASS":
            break
        streak.append(proof)

    if len(streak) < threshold:
        return 0

    common = set(streak[0].get("failed_checks") or [])
    for proof in streak[1:]:
        common &= set(proof.get("failed_checks") or [])
    if not common:
        return 0

    if os.environ.get("LOOP_ACK") == "1":
        print(
            f"[loop] human override (LOOP_ACK=1) — proceeding. "
            f"Streak: {len(streak)} consecutive fails on {sorted(common)}"
        )
        return 0

    sys.stderr.write(
        f"""[loop] DOOM LOOP DETECTED — verification blocked.
  {len(streak)} consecutive FAIL proofs with the same failing check(s): {", ".join(sorted(common))}
  This pattern means the current fix strategy is not working. Patching harder will not help.

  Required protocol:
    1. STOP patching. Re-read the failing test, the task, and the plan.
    2. Write a '## Failure analysis' entry in specs/tasks/ACTIVE.md:
       what was tried, why each attempt failed, the new hypothesis.
    3. A HUMAN reviews it and re-runs:  make verify LOOP_ACK=1

  (Agents may not set LOOP_ACK; the Bash gate blocks it. This escalation is the contract.)
"""
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
