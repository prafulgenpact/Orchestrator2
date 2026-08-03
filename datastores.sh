#!/usr/bin/env bash
#
# datastores.sh — bring up the local datastores the sibling apps need.
#
# Today exactly one app hard-requires a datastore: ArXiv Paper Guide needs PostgreSQL on :5432 with
# a database named 'arxiv_explorer'. (Coding Playground and Blogs Playground boot fine without their
# MySQL/Redis — those are optional; add them only if you use those apps' DB-backed features.)
#
# ArXiv creates its own tables on startup, so this only needs Postgres running + the empty database.
# Idempotent: safe to run again. After it succeeds, run ./run.sh (or ./run.sh --check).
#
set -euo pipefail

PG_FORMULA="postgresql@16"     # already installed on this machine via Homebrew
DB_NAME="arxiv_explorer"

if ! command -v brew >/dev/null 2>&1; then
  echo "✗ Homebrew not found. Alternatives:" >&2
  echo "    • start Docker Desktop, then run a postgres container on :5432 with db '$DB_NAME', or" >&2
  echo "    • install Postgres another way and create the '$DB_NAME' database." >&2
  exit 1
fi

if ! brew list "$PG_FORMULA" >/dev/null 2>&1; then
  echo "· installing $PG_FORMULA ..."
  brew install "$PG_FORMULA"
fi

# The formula's client tools (pg_isready/createdb/psql) aren't on PATH by default.
PG_BIN="$(brew --prefix "$PG_FORMULA")/bin"
export PATH="$PG_BIN:$PATH"
PGDATA="$(brew --prefix)/var/postgresql@16"

wait_ready() {  # returns 0 if Postgres accepts connections within ~12s
  for _ in $(seq 1 12); do
    pg_isready -q -h 127.0.0.1 -p 5432 && return 0
    sleep 1
  done
  return 1
}

# A postmaster.pid left behind by an unclean shutdown blocks startup even though nothing is running.
# Clear it — but ONLY when the PID it records is not actually a live postgres (safe: no server to
# disturb). This is the exact failure that bit us: the OS had recycled the recorded PID.
clear_stale_lock() {
  [ -f "$PGDATA/postmaster.pid" ] || return 0
  local pid comm
  pid="$(head -1 "$PGDATA/postmaster.pid" 2>/dev/null || true)"
  comm="$(ps -p "${pid:-0}" -o comm= 2>/dev/null || true)"
  if printf '%s' "$comm" | grep -qi postgres; then
    return 1  # a real postmaster owns it — do NOT touch
  fi
  echo "· clearing a stale postmaster.pid (recorded pid ${pid:-?} is not postgres)"
  brew services stop "$PG_FORMULA" >/dev/null 2>&1 || true
  sleep 1
  rm -f "$PGDATA/postmaster.pid"
}

echo "· starting $PG_FORMULA (Homebrew service) ..."
brew services start "$PG_FORMULA" >/dev/null
echo -n "· waiting for Postgres on 127.0.0.1:5432 "
if ! wait_ready; then
  echo "(retrying)"
  clear_stale_lock || true
  brew services start "$PG_FORMULA" >/dev/null
  echo -n "· waiting again "
fi
if ! wait_ready; then
  echo
  echo "✗ Postgres did not become ready on :5432. Recent log:" >&2
  tail -8 "$(brew --prefix)/var/log/postgresql@16.log" 2>/dev/null >&2 || true
  exit 1
fi
echo "ready"

# Create the database if it isn't there yet (createdb errors if it exists — that's fine).
if createdb -h 127.0.0.1 -p 5432 "$DB_NAME" 2>/dev/null; then
  echo "· created database '$DB_NAME'"
else
  echo "· database '$DB_NAME' already present"
fi

echo "✓ Postgres is up on :5432 and '$DB_NAME' exists — ArXiv Paper Guide can now start."
echo "  Next: ./run.sh   (verify with ./run.sh --check)"
echo "  To stop Postgres later: brew services stop $PG_FORMULA"
