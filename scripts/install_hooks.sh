#!/usr/bin/env bash
# One-time per clone: activate the git enforcement layer.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath githooks
chmod +x githooks/* scripts/*.sh scripts/*.py 2>/dev/null || true
echo "[hooks] core.hooksPath -> githooks  (pre-commit + pre-push active)"
echo "[hooks] contract live: no push without a fresh committed PASS proof."
