#!/usr/bin/env bash
# Record a planner fixture for every case in cases.json, so the eval can replay offline.
#
# Needs live Foundry credentials (repo-root .env or the sibling app's .env) and network.
# Each run is the sanctioned dry-run CLI path, so the recorded request hash matches what
# tests/eval/test_decomposition.py builds -> the fixtures replay by hash. Re-runnable:
# an already-recorded case is simply overwritten.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"

export AGENT_LLM_MODE=record
export AGENT_LLM_FIXTURES="$here/fixtures"
mkdir -p "$AGENT_LLM_FIXTURES"

# One task per line, straight from the single source of truth (cases.json).
python3 -c 'import json,sys; print("\n".join(c["task"] for c in json.load(open(sys.argv[1]))["cases"]))' \
  "$here/cases.json" | while IFS= read -r task; do
  [ -z "$task" ] && continue
  echo ">> recording: $task"
  PYTHONPATH="$root/src" python3 -m orchestrator "$task" >/dev/null
done

echo "done — fixtures written to $AGENT_LLM_FIXTURES"
echo "now run: make verify   (or: PYTHONPATH=src python -m pytest tests/eval -v)"
