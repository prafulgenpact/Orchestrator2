#!/usr/bin/env bash
# PreToolUse gate for the agent's Edit/Write tools (Claude Code hook).
# 1. Agents may not modify the enforcement layer, forge proofs, or rewrite the objective.
# 2. Plan-then-execute is mechanical: no code edits without an ACTIVE task
#    (REQUIRE_ACTIVE_TASK=0 in verify.config disables — human decision).
# Paths are canonicalized (realpath) so ./ segments and symlinks cannot evade matching.
# Humans edit everything freely in their editor — hooks only intercept agent tools.
set -uo pipefail

INPUT=$(cat)
FP=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)
[ -z "$FP" ] && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
[ -f "$ROOT/verify.config" ] && . "$ROOT/verify.config" 2>/dev/null

# canonical relative path (handles ../, ./, symlinks); files outside the project pass through
REL=$(python3 - "$FP" "$ROOT" <<'EOF'
import os
import sys

fp, root = sys.argv[1], sys.argv[2]
if not os.path.isabs(fp):
    fp = os.path.join(root, fp)
print(os.path.relpath(os.path.realpath(fp), os.path.realpath(root)))
EOF
)
case "$REL" in ..*|"") exit 0 ;; esac

deny() {
  echo "BLOCKED: $1" >&2
  exit 2
}

case "$REL" in
  proofs/*)
    deny "proofs/ is generated evidence — never hand-written. Run 'make verify' to produce a proof." ;;
  githooks/*|scripts/*|verify.config|.proofignore|Makefile|scaffold.manifest|VERSION|.secretsallow)
    deny "'$REL' is enforcement infrastructure. Propose the change to the human; do not modify it yourself." ;;
  .claude/settings.json|.claude/hooks/*)
    deny "hook configuration is the contract itself — humans only." ;;
  specs/00-objective.md)
    deny "the objective is immutable during a build. If it truly must change, the human changes it." ;;
  .github/workflows/*)
    deny "CI is the server-side enforcement layer — humans only." ;;
esac

# Meta files are always writable (plans, docs, state — planning IS allowed without a task)
case "$REL" in
  specs/*|docs/*|*.md|CHANGELOG*|LICENSE*)
    exit 0 ;;
esac

# Plan-then-execute: code edits require an ACTIVE task with a filled Scope
if [ "${REQUIRE_ACTIVE_TASK:-1}" = "1" ] && [ ! -e "$ROOT/specs/tasks/ACTIVE.md" ]; then
  deny "no active task. Plan first: 'make task NAME=...' then fill Goal/Type/Scope/Acceptance in specs/tasks/ACTIVE.md — after that, code edits are allowed."
fi

exit 0
