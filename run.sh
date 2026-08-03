#!/usr/bin/env bash
#
# run.sh — start the Orchestrator (Atelier) app and open it in your browser.
#
# In this project there is ONE server to start, not two: the connector
# (`python -m orchestrator.web`) both serves the web UI (the "frontend") and runs the
# orchestration + live SSE stream (the "backend"). It also launches the 11 sibling apps
# (ports 8001–8011) on demand the first time a task needs them — so you don't start those
# yourself.
#
# Usage:
#   ./run.sh                 # start on port 8080 and open the browser
#   ./run.sh 8090            # start on a different port
#   ATELIER_PORT=8090 ./run.sh
#   NO_OPEN=1 ./run.sh       # start but don't auto-open the browser
#
set -euo pipefail

# Always operate from the repo root (the dir this script lives in).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${1:-${ATELIER_PORT:-8080}}"
URL="http://127.0.0.1:${PORT}/"

# 1) Load credentials from the project-local .env (gitignored), if present, so live runs work.
if [ -f .env ]; then
  set -a; . ./.env; set +a
  echo "· loaded .env"
fi

# 2) Free the port: stop any connector already listening there. This guarantees you always run
#    the CURRENT code (a long-lived old process serves the new HTML but stale Python — see RUNBOOK).
OLD_PID="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
if [ -n "$OLD_PID" ]; then
  echo "· stopping existing server on :$PORT (pid $OLD_PID)"
  kill $OLD_PID 2>/dev/null || true
  sleep 1
fi

# 3) Start the connector (backend + UI). Runs in the background so we can health-check and open it.
echo "· starting Orchestrator on ${URL}"
PYTHONPATH=src ATELIER_PORT="$PORT" python3 -m orchestrator.web &
SERVER_PID=$!

# Stop the server cleanly on Ctrl-C / termination.
cleanup() { echo; echo "· stopping (pid $SERVER_PID)"; kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

# 4) Wait until it answers (or the process dies), then open the browser.
for _ in $(seq 1 40); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "✗ server exited during startup — see the output above (missing deps or bad .env?)" >&2
    exit 1
  fi
  if curl -sf "$URL" -o /dev/null 2>/dev/null; then
    break
  fi
  sleep 0.5
done

if [ "${NO_OPEN:-}" != "1" ]; then
  if command -v open >/dev/null 2>&1; then open "$URL"          # macOS
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" # Linux
  fi
fi

echo "✓ Orchestrator is running at ${URL}  —  press Ctrl-C to stop."
# Keep the script in the foreground tied to the server; exit when the server exits.
wait "$SERVER_PID"
