#!/usr/bin/env bash
# SessionStart hook: re-anchor EVERY session on the objective, the active task,
# project state, and proof status. This is the primary defense against context
# rot — the north star is re-injected no matter how long the project runs.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

python3 <<'EOF'
import json
import os
import subprocess
from pathlib import Path


def head(path: str, n: int) -> str:
    f = Path(path)
    if not f.exists():
        return f"({path} missing — create it before coding)"
    return "\n".join(f.read_text().splitlines()[:n])


def run(cmd: list[str], timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"(unavailable: {e})"


# Large-repo guard: fingerprinting tens of thousands of files inside a session
# hook would blow the hook timeout and silently drop the anchor. Skip the proof
# check above the threshold; everything else still injects.
try:
    n_files = len(run(["git", "ls-files"], timeout=10).splitlines())
except Exception:
    n_files = 0
max_files = int(os.environ.get("SESSION_BRIEF_MAX_FILES", "20000"))
if n_files and n_files > max_files:
    proof = f"(repo has {n_files} files — proof check skipped in session brief; run 'make status')"
else:
    proof = run(["python3", "scripts/check_proof.py"])
loop = run(["python3", "scripts/loop_detector.py"]) or "no doom loop detected"

ctx = f"""=== PROJECT ANCHOR (auto-injected every session — this is the contract) ===

--- Objective (IMMUTABLE, specs/00-objective.md) ---
{head("specs/00-objective.md", 40)}

--- Active task (specs/tasks/ACTIVE.md) ---
{head("specs/tasks/ACTIVE.md", 45)}

--- Project state (STATE.md) ---
{head("STATE.md", 30)}

--- Proof status ---
{proof}

--- Doom-loop status ---
{loop}

Standing rules (non-negotiable, see CLAUDE.md):
- Work ONLY the active task. Plan before code. Small steps.
- Definition of done = 'make verify' PASS + 'make seal'. Nothing else counts as done.
- Bugfixes start with a failing test that reproduces the bug.
- If the same check fails 3x: stop, write '## Failure analysis' in the task, escalate to the human.
- Never touch enforcement files, never bypass hooks, never edit proofs/."""

print(json.dumps({"additionalContext": ctx}))
EOF
