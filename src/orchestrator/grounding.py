"""Relevance guard: confirm an app's results actually address the task.

Apps like arXiv fuzzy-match any text and return *something* for any query, so "the data came
from a real app" is not the same as "the data is relevant". After a successful call, this decides
whether the result is USABLE. Two layers, so the decision is not left purely to an LLM's discretion:

1. A deterministic gate (no LLM call): genuinely empty output (None / blank string / empty
   list / empty dict) is a hard FAIL — there is nothing to use.
2. An LLM judge for everything else, shown the app's FULL output (never a truncated summary) and
   governed by explicit PASS/FAIL rules (see ``relevance_system.md``): PASS unless the output is
   clearly empty, off-topic, or an error. It biases toward PASS and fails OPEN (treat as relevant)
   if the check itself errors or can't be parsed — the guard is a safety net for clearly-wrong
   answers, not a strict quality bar, so a broken/uncertain net must never discard a good result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMClient, LLMError, LLMRequest
from orchestrator.models import Subtask

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "relevance_system.md"
_MAX_TOKENS = 300  # the verdict is tiny; the app's full output goes in the *request*, uncapped


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _is_blank(output: Any) -> bool:
    """True when the app returned nothing usable — the one deterministic FAIL (no LLM needed)."""
    if output is None:
        return True
    if isinstance(output, str):
        return not output.strip()
    if isinstance(output, list | tuple | set | dict):
        return len(output) == 0
    return False  # a number/bool/other scalar is content


def _render_full(output: Any) -> str:
    """The app's COMPLETE output as text for the judge — no truncation, no summarizing."""
    if isinstance(output, str):
        return output
    return json.dumps(output, default=str, ensure_ascii=False)


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def check_relevance(
    client: LLMClient, subtask: Subtask, output: Any, *, model: str
) -> tuple[bool, str]:
    """Judge whether ``output`` is a usable answer to ``subtask``. Returns (relevant, reason).

    Deterministic gate first, then an LLM judge over the FULL output that fails open on any error.
    """
    if _is_blank(output):
        return False, "the app returned no content"

    message = (
        f"TASK:\n{subtask.title}: {subtask.description}\n\n"
        f"APP OUTPUT (full):\n{_render_full(output)}\n\n"
        'Return one raw JSON object: {"verdict": "PASS" | "FAIL", "reason": "<short>"}.'
    )
    request = LLMRequest(
        model=model,
        system=load_system_prompt(),
        messages=({"role": "user", "content": message},),
        max_tokens=_MAX_TOKENS,
    )
    try:
        raw = client.complete(request)
        payload = json.loads(_strip_fences(raw))
    except (LLMError, json.JSONDecodeError):
        return True, ""  # fail open: never hide results on a check error
    if not isinstance(payload, dict):
        return True, ""
    verdict = payload.get("verdict")
    reason = str(payload.get("reason", ""))
    if isinstance(verdict, str) and verdict.strip().upper() == "FAIL":
        return False, reason or "the output does not address the task"
    return True, reason  # PASS, or any unrecognized verdict -> keep the result (fail open)
