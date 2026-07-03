"""Scenario-based E2E for agentic AI systems.

Each tests/e2e/scenarios/*.json is one scripted run of your REAL agent:
input in, artifacts out, assertions on what actually happened — exit code,
output content/structure, files produced. No mocking of your own code.

Determinism rules (see tests/e2e/fixtures/README.md):
  - temperature 0 / fixed seeds wherever your stack allows
  - RECORDED model responses for CI (record once, replay forever)
  - assert on STRUCTURE and FACTS (keys, files, must-contain strings, regex),
    never on exact model prose
  - keep one live-model smoke scenario OUT of CI (run nightly / pre-release)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
CFG = json.loads((HERE / "e2e.config.json").read_text())
SCENARIOS = sorted((HERE / "scenarios").glob("*.json"))

pytestmark = pytest.mark.skipif(
    not CFG.get("configured"),
    reason="e2e not configured: edit tests/e2e/e2e.config.json, set configured=true",
)


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario(path: Path, tmp_path: Path) -> None:
    sc = json.loads(path.read_text())
    env = {**os.environ, **CFG.get("env", {}), **sc.get("env", {})}
    env.setdefault("AGENT_WORKDIR", str(tmp_path))
    cmd = f"{CFG['agent_cmd']} {sc.get('args', '')}".strip()

    r = subprocess.run(
        cmd,
        shell=True,
        input=sc.get("stdin", ""),
        capture_output=True,
        text=True,
        timeout=sc.get("timeout_s", 300),
        env=env,
        cwd=tmp_path,
        check=False,
    )

    exp = sc["expect"]
    assert r.returncode == exp.get("exit_code", 0), f"stderr tail: {r.stderr[-2000:]}"
    for needle in exp.get("stdout_contains", []):
        assert needle in r.stdout, f"stdout missing {needle!r}"
    for pattern in exp.get("stdout_regex", []):
        assert re.search(pattern, r.stdout), f"stdout does not match /{pattern}/"
    for rel in exp.get("files_exist", []):
        assert (tmp_path / rel).exists(), f"expected artifact missing: {rel}"
    for key in exp.get("json_stdout_keys", []):
        assert key in json.loads(r.stdout), f"json stdout missing key {key!r}"
