# Changelog

All notable changes. One entry per merged task; newest first.
Format: `## [date] task-id — summary (proof commit sha)`

## [scaffold 1.2.0] — audit fixes

- auto-seal now requires a fully clean tree incl. untracked files (fingerprint alignment)
- STALE messages explain untracked-file and merge-commit causes
- pip-audit scoped to project requirements files, not the whole environment
- plan-then-execute mechanically enforced (REQUIRE_ACTIVE_TASK, gate_edit)
- gate_edit canonicalizes paths (no ./ or symlink evasion); LOOP_ACK gate assignment-only
- secret scanner catches unquoted .env-style assignments
- web e2e junit parsed into proofs; update script new-file output fixed
- session brief guards against large-repo hook timeouts
- wizard re-run never destroys a filled objective (consent + backup)
- installer: Windows refusal, corruption detection, clean abort handling
- BOOTSTRAP_LATEST=1 fallback for pin/interpreter mismatches

## [unreleased]

- scaffold initialized
