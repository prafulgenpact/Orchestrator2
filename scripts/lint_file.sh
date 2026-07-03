#!/usr/bin/env bash
# PostToolUse hook: immediately lint whatever the agent just wrote or edited.
# Auto-fixes what tools can fix; anything left is fed back (exit 2) so the
# agent fixes it NOW, in context — not 40 edits later.
set -uo pipefail

INPUT=$(cat)
FP=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)

if [ -z "$FP" ] || [ ! -f "$FP" ]; then
  exit 0
fi

case "$FP" in
  *.py)
    command -v ruff >/dev/null 2>&1 || exit 0
    ruff format "$FP" >/dev/null 2>&1 || true
    if ! OUT=$(ruff check --fix "$FP" 2>&1); then
      {
        echo "ruff still reports problems in $FP — fix them now:"
        echo "$OUT"
      } >&2
      exit 2
    fi
    ;;
  *.ts|*.tsx|*.js|*.jsx)
    [ -f "${CLAUDE_PROJECT_DIR:-.}/web/package.json" ] || exit 0
    (cd "${CLAUDE_PROJECT_DIR:-.}/web" && npx prettier --log-level warn --write "$FP") >/dev/null 2>&1 || true
    if ! OUT=$(cd "${CLAUDE_PROJECT_DIR:-.}/web" && npx eslint --fix "$FP" 2>&1); then
      {
        echo "eslint still reports problems in $FP — fix them now:"
        echo "$OUT"
      } >&2
      exit 2
    fi
    ;;
esac

exit 0
