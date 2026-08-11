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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import Artifact, PlanResult, SubtaskResult

# A sink for streamed answer text; the CLI passes one to show the answer live, others omit it.
DeltaFn = Callable[[str], None]

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "synthesis_system.md"
_MAX_TOKENS = 4000  # headroom so a fused multi-result answer (with code/blog excerpts) isn't cut
_RESULT_LIMIT = 3000  # chars per result fed to the synthesizer — bounded for tokens


@dataclass(frozen=True)
class Synthesis:
    """The orchestrator's final answer for an executed plan.

    ``mode`` is "verbatim" (a lone app's prose passed through untouched), "final-step" (a single
    terminal step that already consumed the others, passed through), "synthesized" (results fused
    by one LLM call), or "none" (no app produced a grounded result). ``sources`` are the provenance
    URLs of the results the answer is grounded in — collected in code, never invented.
    """

    answer: str
    mode: str
    sources: tuple[str, ...]
    artifacts: tuple[Artifact, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "mode": self.mode,
            "sources": list(self.sources),
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _ok_results(plan_result: PlanResult) -> tuple[SubtaskResult, ...]:
    """The results that actually produced grounded data (status "ok")."""
    return tuple(r for r in plan_result.results if r.status == "ok")


# Human, grounded phrasing for each way a chosen app can fail to deliver — so the answer explains
# WHAT happened (never a web substitute, never a bland "no answer"). The concrete error detail
# from the result is appended by the caller; these are the lead-ins.
_FAILURE_LEADIN = {
    "skipped": "needed information the task did not provide",
    "no_match": "did not return results that matched the task",
    "error": "could not complete the request",
}


def _failed_results(plan_result: PlanResult) -> tuple[SubtaskResult, ...]:
    """Results from chosen apps that did NOT produce grounded data (error/skipped/no_match)."""
    return tuple(r for r in plan_result.results if r.status != "ok")


def _failure_line(r: SubtaskResult) -> str:
    """One honest, grounded line: which app, and why it could not complete this subtask."""
    lead = _FAILURE_LEADIN.get(r.status, "could not complete the request")
    detail = f" ({r.error})" if r.error else ""
    return f"- {r.app_name} {lead}{detail}"


def _sources(ok: Sequence[SubtaskResult]) -> tuple[str, ...]:
    """Unique source URLs of the ok results, in order — provenance from code, not the model."""
    seen: list[str] = []
    for r in ok:
        if r.source and r.source not in seen:
            seen.append(r.source)
    return tuple(seen)


def _artifacts(ok: Sequence[SubtaskResult]) -> tuple[Artifact, ...]:
    """All chart artifacts from the ok results — carried separately so they never enter the LLM
    prompt or the text length caps (a chart is not text and must not be truncated)."""
    return tuple(a for r in ok for a in r.artifacts)


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


def _failed_block(failed: Sequence[SubtaskResult]) -> str:
    """What each step that produced nothing was supposed to do, and why it did not."""
    lines: list[str] = []
    for r in failed:
        detail = f" — {r.error}" if r.error else ""
        lines.append(f"[{r.subtask_id}] {r.app_name} ({r.status}){detail}")
    return "\n".join(lines)


def build_synthesis_message(
    task: str, ok: Sequence[SubtaskResult], failed: Sequence[SubtaskResult] = ()
) -> str:
    """The synthesizer's user message: what succeeded AND what did not.

    Both halves matter. Given only the successes it cannot tell which parts of the task went
    unanswered, so it answers the whole task and fills the gaps from general knowledge — the
    2026-08-11 HR run described an EDA and a model that never ran.
    """
    parts = [
        f"TASK:\n{task}",
        f"RESULTS (from the apps that ran — use only these):\n{_results_block(ok)}",
    ]
    if failed:
        parts.append(
            "STEPS THAT PRODUCED NOTHING (these did NOT run — you must not describe their work "
            f"as if it happened):\n{_failed_block(failed)}"
        )
    parts.append(
        "Write ONE grounded answer to the task in the user's voice, using only the results above."
    )
    return "\n\n".join(parts)


def _emit(on_delta: DeltaFn | None, text: str) -> None:
    """Feed a whole answer to the sink at once (used by the pass-through modes, and as the fallback
    when the client can't stream) so the CLI shows the same text either way."""
    if on_delta is not None:
        on_delta(text)


def _synthesize_llm(
    client: LLMClient,
    task: str,
    ok: Sequence[SubtaskResult],
    *,
    model: str,
    on_delta: DeltaFn | None = None,
    failed: Sequence[SubtaskResult] = (),
) -> str:
    request = LLMRequest(
        model=model,
        system=load_system_prompt(),
        messages=({"role": "user", "content": build_synthesis_message(task, ok, failed)},),
        max_tokens=_MAX_TOKENS,
    )
    # Stream the fused answer live when the client supports it; otherwise fall back to a blocking
    # complete() and emit the whole string once. Replay/Recording clients (tests/CI) take the
    # fallback, so determinism and recorded fixtures are unaffected.
    stream_fn = getattr(client, "complete_stream", None)
    if on_delta is not None and callable(stream_fn):
        return str(stream_fn(request, on_delta)).strip()
    text = client.complete(request).strip()
    _emit(on_delta, text)
    return text


def _dominant_terminal(
    ok: Sequence[SubtaskResult], subtask_deps: dict[str, tuple[str, ...]] | None
) -> SubtaskResult | None:
    """The single terminal ok step that already consumed the others, if any.

    A terminal step is one no other subtask depends on; it is "dominant" when it is the ONLY such
    ok step and it depends on at least one other ok step (so its output already folds in the
    upstream work). Its prose is the finished answer — re-fusing it would be redundant and lossy.
    Returns None (fall back to fusing) when the dependency graph isn't known or has no clear sink.
    """
    if subtask_deps is None or len(ok) < 2:
        return None
    ok_ids = {r.subtask_id for r in ok}
    depended_upon = {dep for deps in subtask_deps.values() for dep in deps}
    terminals = [r for r in ok if r.subtask_id not in depended_upon]
    if len(terminals) != 1:
        return None
    terminal = terminals[0]
    if not any(dep in ok_ids for dep in subtask_deps.get(terminal.subtask_id, ())):
        return None  # a lone step that consumed nothing is not a synthesis of the others
    return terminal


def synthesize(
    client: LLMClient,
    plan_result: PlanResult,
    *,
    model: str,
    subtask_deps: dict[str, tuple[str, ...]] | None = None,
    on_delta: DeltaFn | None = None,
) -> Synthesis:
    """Collapse an executed plan into one grounded answer.

    ``subtask_deps`` (subtask id -> its depends_on) lets a single terminal step that already
    consumed the others be passed through verbatim instead of re-fused (avoids redundant,
    truncating re-summarization of a long final result).

    ``on_delta``, when given, receives the answer as it is produced — streamed token-by-token on
    the LLM-fusion path, or emitted whole for the pass-through modes — so the CLI can show it live.
    """
    ok = _ok_results(plan_result)
    sources = _sources(ok)
    artifacts = _artifacts(ok)
    failed = _failed_results(plan_result)

    def _disclose(answer: str) -> str:
        """Append the honest note about steps that produced nothing.

        Mechanical on purpose. The prompt asks the writer to report failures, but a request is
        not a guarantee — and the pass-through modes never consult a model at all, so one app's
        tuned prose would otherwise hide every failure around it.
        """
        if not failed:
            return answer
        lines = "\n".join(_failure_line(r) for r in failed)
        return f"{answer}\n\n---\n\nNot completed in this run:\n{lines}"

    if not ok:
        # No app produced grounded data. Be honest about WHY (per app), not bland — and never
        # reach for the web here: web is only the planner's no-app route, not a runtime rescue.
        if failed:
            answer = "This task could not be completed by the selected apps:\n" + "\n".join(
                _failure_line(r) for r in failed
            )
        else:
            answer = "No app returned a grounded result for this task, so there is no answer."
        _emit(on_delta, answer)
        return Synthesis(answer=answer, mode="none", sources=())
    terminal = _dominant_terminal(ok, subtask_deps)
    if terminal is not None and isinstance(terminal.output, str) and terminal.output.strip():
        # The final step already folded in the upstream results — pass it through, don't re-fuse.
        answer = _disclose(terminal.output.strip())
        _emit(on_delta, answer)
        return Synthesis(answer=answer, mode="final-step", sources=sources, artifacts=artifacts)
    only = ok[0]
    if len(ok) == 1 and isinstance(only.output, str) and only.output.strip():
        # One app fully answered in prose — pass it through verbatim to keep its tuned voice.
        answer = _disclose(only.output.strip())
        _emit(on_delta, answer)
        return Synthesis(answer=answer, mode="verbatim", sources=sources, artifacts=artifacts)
    answer = _disclose(
        _synthesize_llm(client, plan_result.task, ok, model=model, on_delta=on_delta, failed=failed)
    )
    return Synthesis(answer=answer, mode="synthesized", sources=sources, artifacts=artifacts)
