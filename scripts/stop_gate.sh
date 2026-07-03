#!/usr/bin/env bash
# Stop hook: the agent may not declare completion while unverified changes exist.
# "It works now" is not evidence. A matching PASS proof is.
# stop_hook_active guard prevents infinite loops: the agent gets exactly one
# forced continuation ("go verify"), then may stop.
set -uo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

INPUT=$(cat)
ACTIVE=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("stop_hook_active", False)).lower())' 2>/dev/null || echo false)
[ "$ACTIVE" = "true" ] && exit 0

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
cd "$(git rev-parse --show-toplevel)"

# Current code state already covered by a valid PASS proof? Fine, stop.
if python3 "$SCRIPT_DIR/check_proof.py" --quiet 2>/dev/null; then
  exit 0
fi

# No verified proof — but only intervene if there is actual unfinished work:
# uncommitted changes, or local commits that were never pushed.
UNCOMMITTED=$(git status --porcelain)
UNPUSHED=$(git log --branches --not --remotes --oneline 2>/dev/null || true)
if [ -z "$UNCOMMITTED" ] && [ -z "$UNPUSHED" ]; then
  exit 0
fi

{
  echo "STOP BLOCKED by contract: the current code state has no matching PASS proof."
  echo "Before finishing:"
  echo "  1. Run 'make verify'."
  echo "  2. If it FAILS: report the failure honestly, with the failing check names. Do not claim success."
  echo "  3. If it PASSES: run 'make seal', then summarize the evidence from proofs/latest.json"
  echo "     (checks run, test counts, coverage, fingerprint)."
} >&2
exit 2
