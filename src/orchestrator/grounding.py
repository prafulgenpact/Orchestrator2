"""Relevance guard: confirm an app's results actually address the task (one LLM check).

Apps like arXiv fuzzy-match any text and return *something* for any query, so "the data came
from a real app" is not the same as "the data is relevant". After a successful call, this asks
the model whether a compact summary of the results genuinely addresses the subtask. It fails
OPEN (treat as relevant) if the check itself can't be parsed — the guard is a safety net, not a
hard gate, so a broken net must not hide good results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import Subtask

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "relevance_system.md"
_MAX_TOKENS = 300
_SUMMARY_LIMIT = 1500


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _summarize(output: Any, limit: int = _SUMMARY_LIMIT) -> str:
    """A compact, judge-friendly view of an app's output (titles/names for list items)."""
    if isinstance(output, list):
        items: list[str] = []
        for item in output[:8]:
            if isinstance(item, dict):
                label = item.get("title") or item.get("name") or item.get("id") or item
                items.append(str(label))
            else:
                items.append(str(item))
        return "; ".join(items)[:limit]
    text = output if isinstance(output, str) else json.dumps(output, default=str)
    return " ".join(text.split())[:limit]


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
    """Judge whether ``output`` addresses ``subtask``. Returns (relevant, reason)."""
    message = (
        f"TASK:\n{subtask.title}: {subtask.description}\n\n"
        f"RESULTS (summary):\n{_summarize(output)}\n\n"
        'Return one raw JSON object: {"relevant": true|false, "reason": "<short>"}.'
    )
    request = LLMRequest(
        model=model,
        system=load_system_prompt(),
        messages=({"role": "user", "content": message},),
        max_tokens=_MAX_TOKENS,
    )
    raw = client.complete(request)
    try:
        payload = json.loads(_strip_fences(raw))
        if not isinstance(payload, dict):
            return True, ""
        return bool(payload.get("relevant", True)), str(payload.get("reason", ""))
    except json.JSONDecodeError:
        return True, ""  # fail open: never hide results on a check error
