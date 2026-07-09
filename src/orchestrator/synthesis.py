"""Combine executed-plan results into ONE grounded answer in the user's voice (AC-4).

After the executor has run every subtask, this collapses the per-app results into a single answer
the user reads first. Two paths, both grounded strictly in what the apps returned:

- Verbatim pass-through: when exactly one app produced a prose answer, it is returned unchanged.
  The individual apps are already tuned to the user's voice (AC-4), so re-writing a lone app's
  answer would only risk drift and lost nuance — the orchestrator respects it and makes no LLM call.
- Synthesis: when several apps contributed (or the lone result is structured data), one LLM call
  fuses them into a single answer, using ONLY the provided results. It never adds outside facts —
  accuracy and grounding over fluency.

Sources are computed from the results in code (never trusted from the model), so provenance holds
regardless of what the model writes.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import PlanResult, SubtaskResult

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "synthesis_system.md"
_MAX_TOKENS = 1500
_RESULT_LIMIT = 3000  # chars per result fed to the synthesizer — bounded for tokens


@dataclass(frozen=True)
class Synthesis:
    """The orchestrator's final answer for an executed plan.

    ``mode`` is "verbatim" (one app's prose passed through untouched), "synthesized" (results
    fused by one LLM call), or "none" (no app produced a grounded result). ``sources`` are the
    provenance URLs of the results the answer is grounded in — collected in code, never invented.
    """

    answer: str
    mode: str
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "mode": self.mode, "sources": list(self.sources)}


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _ok_results(plan_result: PlanResult) -> tuple[SubtaskResult, ...]:
    """The results that actually produced grounded data (status "ok")."""
    return tuple(r for r in plan_result.results if r.status == "ok")


def _sources(ok: Sequence[SubtaskResult]) -> tuple[str, ...]:
    """Unique source URLs of the ok results, in order — provenance from code, not the model."""
    seen: list[str] = []
    for r in ok:
        if r.source and r.source not in seen:
            seen.append(r.source)
    return tuple(seen)


def _render_output(output: Any, limit: int = _RESULT_LIMIT) -> str:
    """A content-preserving, length-bounded view of one app's output for the synthesizer."""
    if isinstance(output, str):
        text = output.strip()
    else:
        text = json.dumps(output, default=str, ensure_ascii=False).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _results_block(ok: Sequence[SubtaskResult]) -> str:
    blocks: list[str] = []
    for r in ok:
        head = f"[{r.subtask_id}] {r.app_name}"
        if r.operation:
            head += f" ({r.operation})"
        blocks.append(f"{head}:\n{_render_output(r.output)}")
    return "\n\n".join(blocks)


def build_synthesis_message(task: str, ok: Sequence[SubtaskResult]) -> str:
    return (
        f"TASK:\n{task}\n\n"
        f"RESULTS (from the apps that ran — use only these):\n{_results_block(ok)}\n\n"
        "Write ONE grounded answer to the task in the user's voice, using only the results above."
    )


def _synthesize_llm(
    client: LLMClient, task: str, ok: Sequence[SubtaskResult], *, model: str
) -> str:
    request = LLMRequest(
        model=model,
        system=load_system_prompt(),
        messages=({"role": "user", "content": build_synthesis_message(task, ok)},),
        max_tokens=_MAX_TOKENS,
    )
    return client.complete(request).strip()


def synthesize(client: LLMClient, plan_result: PlanResult, *, model: str) -> Synthesis:
    """Collapse an executed plan into one grounded answer (verbatim, synthesized, or none)."""
    ok = _ok_results(plan_result)
    sources = _sources(ok)
    if not ok:
        return Synthesis(
            answer="No app returned a grounded result for this task, so there is no answer.",
            mode="none",
            sources=(),
        )
    only = ok[0]
    if len(ok) == 1 and isinstance(only.output, str) and only.output.strip():
        # One app fully answered in prose — pass it through verbatim to keep its tuned voice.
        return Synthesis(answer=only.output.strip(), mode="verbatim", sources=sources)
    answer = _synthesize_llm(client, plan_result.task, ok, model=model)
    return Synthesis(answer=answer, mode="synthesized", sources=sources)
