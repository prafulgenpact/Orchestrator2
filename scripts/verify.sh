#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# THE single verification entrypoint. Everything green here = "done".
# Produces tamper-evident proof-of-testing in proofs/ (PASS and FAIL alike).
# Deterministic: pinned env, fixed seeds, same checks in the same order.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

# ---- 0) single-flight lock (concurrent verifies corrupt reports/) -----------
LOCKDIR=".verify.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  if [ -n "$(find "$LOCKDIR" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
    rm -rf "$LOCKDIR" && mkdir "$LOCKDIR" 2>/dev/null || { echo "[verify] ⛔ another verification is running"; exit 5; }
    echo "[verify] stale lock (>2h) removed"
  else
    echo "[verify] ⛔ another verification is already running (stale? rm -rf $LOCKDIR)"; exit 5
  fi
fi
trap 'rm -rf "$LOCKDIR"' EXIT

export TZ=UTC PYTHONHASHSEED=0 LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
[ -f verify.config ] && . ./verify.config
export REQUIRED_CHECKS="${REQUIRED_CHECKS:-py-lint py-format py-types py-unit e2e secrets}"
COVERAGE_MIN="${COVERAGE_MIN:-80}"
export STRICT_SCOPE="${STRICT_SCOPE:-0}"
export LOOP_THRESHOLD="${LOOP_THRESHOLD:-3}"

# ---- 1) doom-loop gate (dev machines only; CI always re-verifies fresh) ----
if [ "${CI:-}" != "true" ] && [ "${CI:-}" != "1" ]; then
  python3 scripts/loop_detector.py || exit 3
fi

# ---- 2) clean-tree discipline ----------------------------------------------
# The proof fingerprint covers tracked AND untracked(non-ignored) files — an
# untracked code file is unverified code. Surface both cases explicitly.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "[verify] NOTE: uncommitted changes to tracked files."
  echo "         The proof will bind to the worktree; commit before sealing or the push gate will reject it."
fi
UNTRACKED_FILES=$(git ls-files -o --exclude-standard)
if [ -n "$UNTRACKED_FILES" ]; then
  echo "[verify] NOTE: untracked files are part of the fingerprint (they are code until proven otherwise):"
  printf '%s\n' "$UNTRACKED_FILES" | sed 's/^/           /'
  echo "         Commit them or add to .gitignore before pushing, or the proof will read STALE at push time."
fi

rm -rf reports && mkdir -p reports
: > reports/checks.jsonl

record() { # name status duration
  python3 - "$1" "$2" "${3:-0}" <<'EOF'
import json, sys
rec = {"name": sys.argv[1], "status": sys.argv[2], "duration_s": int(sys.argv[3]),
       "evidence": f"reports/{sys.argv[1]}.log"}
with open("reports/checks.jsonl", "a") as f:
    f.write(json.dumps(rec) + "\n")
EOF
}

run_check() { # name cmd...
  local name="$1"; shift
  local start end status
  start=$(date +%s)
  echo "──── [$name] $*"
  if "$@" >"reports/$name.log" 2>&1; then status=pass; else status=fail; fi
  end=$(date +%s)
  if [ "$status" = fail ]; then
    echo "[$name] ❌ FAIL — evidence: reports/$name.log (last 20 lines)"
    tail -n 20 "reports/$name.log" | sed 's/^/    /'
  else
    echo "[$name] ✅ pass ($((end - start))s)"
  fi
  record "$name" "$status" "$((end - start))"
}

skip_check() { # name reason
  echo "[$1] ⏭  skip — $2"
  record "$1" "skip" 0
}

have() { command -v "$1" >/dev/null 2>&1; }

# ---- 3) Python checks -------------------------------------------------------
if [ -f pyproject.toml ]; then
  if have ruff; then
    run_check py-lint   ruff check .
    run_check py-format ruff format --check .
  else
    skip_check py-lint "ruff not installed (make bootstrap)"
    skip_check py-format "ruff not installed"
  fi
  if have mypy; then
    run_check py-types mypy ${MYPY_PATHS:-src}
  else
    skip_check py-types "mypy not installed"
  fi
  if have pytest; then
    if [ -d tests/unit ]; then
      run_check py-unit pytest tests/unit -q -p no:cacheprovider \
        --junitxml=reports/junit-unit.xml \
        --cov="${COV_PATHS:-src}" --cov-report=xml:reports/coverage.xml \
        --cov-report=term --cov-fail-under="$COVERAGE_MIN"
    else
      skip_check py-unit "tests/unit/ missing"
    fi
    if [ -d tests/e2e ]; then
      run_check e2e pytest tests/e2e -q -p no:cacheprovider --junitxml=reports/junit-e2e.xml
    else
      skip_check e2e "tests/e2e/ missing"
    fi
  else
    skip_check py-unit "pytest not installed (make bootstrap)"
    skip_check e2e "pytest not installed"
  fi
fi

# ---- 4) Web checks (activate by creating ${WEB_DIR:-web}/package.json) ------
WEB_DIR="${WEB_DIR:-web}"
if [ -f "$WEB_DIR/package.json" ]; then
  run_check web-lint  npm --prefix "$WEB_DIR" run -s lint
  run_check web-types npm --prefix "$WEB_DIR" run -s typecheck
  run_check web-unit  npm --prefix "$WEB_DIR" run -s test:unit
  if [ "${WEB_E2E:-0}" = "1" ]; then
    run_check web-e2e npm --prefix "$WEB_DIR" run -s test:e2e
  fi
fi

# ---- 5) security lane --------------------------------------------------------
run_check secrets python3 scripts/secret_scan.py     # stdlib — always available
if have gitleaks; then
  run_check secrets-gitleaks gitleaks detect --no-banner --redact -s .
fi
if have pip-audit; then
  # Scoped to PROJECT requirements files — never the whole local environment
  # (a vulnerable package unrelated to this project must not fail this proof).
  REQ_ARGS=""
  for req in requirements*.txt; do
    [ -f "$req" ] && REQ_ARGS="$REQ_ARGS -r $req"
  done
  if [ -n "$REQ_ARGS" ]; then
    # shellcheck disable=SC2086
    run_check dep-audit pip-audit --progress-spinner off $REQ_ARGS ${DEP_AUDIT_ARGS:-}
  else
    skip_check dep-audit "no requirements*.txt to audit"
  fi
else
  skip_check dep-audit "pip-audit not installed (optional lane)"
fi
if have diff-cover && [ -f reports/coverage.xml ] && git rev-parse --verify -q "${BASE_BRANCH:-main}" >/dev/null; then
  run_check diff-cover diff-cover reports/coverage.xml \
    --compare-branch "${BASE_BRANCH:-main}" --fail-under "${DIFF_COVERAGE_MIN:-0}"
else
  skip_check diff-cover "diff-cover not installed or no coverage/base branch (optional lane)"
fi

# ---- 5b) extra project checks (verify.config EXTRA_CHECKS="name:cmd;name:cmd")
# For anything beyond the standard lanes: docker build, security scan,
# agent-eval suites, contract tests, etc. Add their names to REQUIRED_CHECKS
# to make them mandatory for a PASS proof.
if [ -n "${EXTRA_CHECKS:-}" ]; then
  IFS=';' read -ra _XCHECKS <<< "$EXTRA_CHECKS"
  for _spec in "${_XCHECKS[@]}"; do
    _name="${_spec%%:*}"
    _cmd="${_spec#*:}"
    [ -n "$_name" ] && [ -n "$_cmd" ] && run_check "$_name" bash -c "$_cmd"
  done
fi

# ---- 6) scope drift (independent of agent self-reporting) -------------------
python3 scripts/drift_check.py || { echo "[verify] ⛔ blocked by scope drift (STRICT_SCOPE=1)"; exit 4; }

# ---- 7) seal results into a proof (FAIL proofs recorded too) ----------------
python3 scripts/gen_proof.py
rc=$?
echo
if [ $rc -eq 0 ]; then
  # auto-seal: on PASS with a FULLY clean tree — including untracked files,
  # because the fingerprint covers them; sealing over untracked files would
  # guarantee a STALE rejection at push time (fingerprint(worktree) != fingerprint(HEAD)).
  # (AUTOSEAL=0 in verify.config restores manual 'make seal'; CI never commits.)
  DIRTY_ALL=$(git status --porcelain -- . ':!proofs')
  if [ "${AUTOSEAL:-1}" = "1" ] && [ "${CI:-}" != "true" ] && [ "${CI:-}" != "1" ] \
     && git rev-parse -q --verify HEAD >/dev/null \
     && [ -z "$DIRTY_ALL" ]; then
    git add proofs/
    if git diff --cached --quiet -- proofs/; then
      echo "[verify] ✅ PASS — proof already sealed. Next: git push"
    else
      git commit -q -m "proof: seal verification for $(git rev-parse --short HEAD)" -- proofs/ \
        && echo "[verify] ✅ PASS — proof auto-sealed. Next: git push"
    fi
  elif [ -n "${DIRTY_ALL:-}" ]; then
    echo "[verify] ✅ PASS — proof written, NOT auto-sealed (uncommitted/untracked files above)."
    echo "         Commit or .gitignore them, then: make verify   (fingerprint must match what you push)"
  else
    echo "[verify] ✅ PASS — proof written. Commit your changes, then: make seal && git push (or make push)"
  fi
else
  echo "[verify] ❌ FAIL — the failure is on record in proofs/. Fix it and re-run make verify."
fi
exit $rc
