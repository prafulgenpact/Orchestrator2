#!/usr/bin/env bash
# Propagate scaffold improvements into an existing project.
#   bash scripts/update_from_scaffold.sh /path/to/newer/agentic-scaffold          # dry run (diffs)
#   bash scripts/update_from_scaffold.sh /path/to/newer/agentic-scaffold --apply  # backup + overwrite
# Only files listed in scaffold.manifest (harness-owned) are ever touched.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

SRC="${1:?usage: update_from_scaffold.sh <newer-scaffold-dir> [--apply]}"
APPLY="${2:-}"
[ -f "$SRC/scaffold.manifest" ] || { echo "[update] $SRC is not a scaffold (no scaffold.manifest)"; exit 1; }

OLD_V=$(cat VERSION 2>/dev/null || echo "unknown")
NEW_V=$(cat "$SRC/VERSION" 2>/dev/null || echo "unknown")
echo "[update] project harness $OLD_V  ->  scaffold $NEW_V"

CHANGED=0
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
while IFS= read -r f; do
  case "$f" in ''|\#*) continue ;; esac
  if [ ! -f "$SRC/$f" ]; then continue; fi
  if [ ! -f "$f" ] || ! cmp -s "$f" "$SRC/$f"; then
    CHANGED=$((CHANGED + 1))
    echo "── $f"
    if [ -f "$f" ]; then
      diff -u "$f" "$SRC/$f" 2>/dev/null | head -40 || true
    else
      echo "   (new file in scaffold)"
    fi
    if [ "$APPLY" = "--apply" ]; then
      mkdir -p ".scaffold-backup/$STAMP/$(dirname "$f")"
      [ -f "$f" ] && cp "$f" ".scaffold-backup/$STAMP/$f"
      mkdir -p "$(dirname "$f")"
      cp "$SRC/$f" "$f"
    fi
  fi
done < "$SRC/scaffold.manifest"

if [ "$CHANGED" -eq 0 ]; then
  echo "[update] already up to date"
elif [ "$APPLY" = "--apply" ]; then
  chmod +x githooks/* scripts/*.sh scripts/*.py 2>/dev/null || true
  echo "[update] $CHANGED file(s) updated; originals in .scaffold-backup/$STAMP/"
  echo "[update] next: make verify (re-establish proof), review 'git diff', commit as 'chore: scaffold $NEW_V'"
else
  echo "[update] dry run: $CHANGED file(s) would change. Apply with: bash scripts/update_from_scaffold.sh $SRC --apply"
fi
