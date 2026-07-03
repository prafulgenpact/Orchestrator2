# Deterministic entrypoints — the only commands humans and agents should use.
SHELL := /usr/bin/env bash
export TZ := UTC
export PYTHONHASHSEED := 0

.PHONY: help init doctor hooks bootstrap verify seal push status audit task clean

doctor: ## diagnose the whole harness: env, toolchain vs pins, hooks, contract state
	@python3 scripts/doctor.py

help: ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-12s %s\n", $$1, $$2}'

init: ## one-time interactive project setup (objective, e2e kit, git, hooks)
	@test -f init.py && python3 init.py || echo "[init] already initialized (init.py removed itself)"

hooks: ## install git hooks (once per clone)
	bash scripts/install_hooks.sh

bootstrap: hooks ## deterministic environment setup (locked deps; BOOTSTRAP_LATEST=1 to re-pin on new interpreters)
	@if [ "$${BOOTSTRAP_LATEST:-0}" = "1" ]; then \
		echo "[bootstrap] installing LATEST toolchain (pin refresh mode)"; \
		python3 -m pip install --upgrade ruff mypy pytest pytest-cov pip-audit diff_cover && \
		echo "[bootstrap] now RE-PIN deliberately — update requirements-dev.txt with:" && \
		python3 -m pip freeze | grep -iE '^(ruff|mypy|pytest|pytest-cov|pytest_cov|pip-audit|pip_audit|diff-cover|diff_cover)==' ; \
	elif [ -f requirements-dev.txt ]; then \
		python3 -m pip install -r requirements-dev.txt || { \
			echo "[bootstrap] pinned install failed — likely a new Python vs old pins."; \
			echo "            Fix: BOOTSTRAP_LATEST=1 make bootstrap   (then update requirements-dev.txt)"; \
			exit 1; }; \
	fi
	@if [ -f web/package.json ]; then npm --prefix web ci; fi
	@echo "[bootstrap] done — run 'make verify' to establish the first proof"

verify: ## run ALL checks and write proof-of-testing (the only definition of done)
	bash scripts/verify.sh

seal: ## commit the proof for the current HEAD (required before push)
	@python3 scripts/check_proof.py || { echo "[seal] no valid proof for current code — run: make verify"; exit 1; }
	@git add proofs/
	@if git diff --cached --quiet -- proofs/; then \
		echo "[seal] proof already sealed for $$(git rev-parse --short HEAD)"; \
	else \
		git commit -m "proof: seal verification for $$(git rev-parse --short HEAD)" -- proofs/; \
		echo "[seal] proof committed"; \
	fi
	@python3 scripts/check_proof.py --ref HEAD

push: ## verify (if needed) + seal + push — the only sanctioned way to publish
	@python3 scripts/check_proof.py --quiet 2>/dev/null || $(MAKE) verify
	@$(MAKE) seal
	git push

status: ## proof validity, doom-loop state, scope drift
	@python3 scripts/check_proof.py || true
	@python3 scripts/loop_detector.py || true
	@python3 scripts/drift_check.py || true

audit: ## independent fresh-context audit of the branch vs objective/plan
	@command -v claude >/dev/null 2>&1 \
		&& claude --agent auditor -p "Audit the current branch for drift against the objective, plan, and active task. Follow your instructions and output your verdict block." \
		|| echo "[audit] claude CLI not found — in a Claude Code session type: @auditor audit the current branch"

task: ## start a new task file: make task NAME=short-name
	@test -n "$(NAME)" || { echo "usage: make task NAME=short-name"; exit 1; }
	@id="$$(date -u +%Y%m%d)-$(NAME)"; \
	cp specs/tasks/TEMPLATE.md "specs/tasks/$$id.md"; \
	ln -sf "$$id.md" specs/tasks/ACTIVE.md; \
	echo "[task] created specs/tasks/$$id.md (now ACTIVE)"; \
	echo "[task] fill in Goal / Type / Scope / Acceptance criteria BEFORE any code is written"

clean: ## remove caches (never removes proofs — they are the record)
	rm -rf reports .pytest_cache .mypy_cache .ruff_cache .coverage
