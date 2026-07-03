#!/usr/bin/env bash
# PreToolUse gate for the agent's Bash tool (Claude Code hook).
# Enforces the human/agent contract at the moment of action.
# stdin: hook JSON. Exit 2 blocks the call; stderr is fed back to the agent.
set -uo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)
[ -z "$CMD" ] && exit 0

deny() {
  echo "CONTRACT VIOLATION BLOCKED: $1" >&2
  exit 2
}

case "$CMD" in
  *--no-verify*)
    deny "--no-verify defeats the verification contract. Fix the failure instead of bypassing the hook." ;;
esac
# Block LOOP_ACK only as an assignment/env prefix (LOOP_ACK=...), not mere
# mentions — reading docs or grepping for it is legitimate.
if printf '%s' "$CMD" | grep -qE '(^|[[:space:];&|])LOOP_ACK='; then
  deny "LOOP_ACK is a human-only override. Report the doom loop to the human and wait for their decision."
fi
case "$CMD" in
  *core.hooksPath*|*hooksPath*)
    deny "git hook configuration is enforcement infrastructure — humans only." ;;
esac
case "$CMD" in
  *push*--force*|*"push -f"*|*--force-with-lease*)
    deny "force-push is disabled for agents. Ask the human if history rewriting is truly needed." ;;
esac

# Best-effort: block shell writes into proofs/ (forgery). gen_proof.py is the only writer.
if printf '%s' "$CMD" | grep -qE '(>|>>|\btee\b|\brm\b|\bmv\b|\bcp\b|\btouch\b|sed -i)[^|]*proofs/'; then
  deny "writing into proofs/ by hand is proof forgery. Proofs are generated only by 'make verify'."
fi

# git push requires a valid committed PASS proof for HEAD — early feedback for the agent.
if printf '%s' "$CMD" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push'; then
  if ! python3 "$SCRIPT_DIR/check_proof.py" --ref HEAD --quiet 2>/dev/null; then
    deny "no valid PASS proof committed for HEAD. Run: make verify && make seal — then push. Evidence, not assertions."
  fi
fi

exit 0
