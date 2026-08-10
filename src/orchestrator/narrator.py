"""Turn one finished step's real result into 1-2 conversational sentences for the task panel.

The web UI shows each step's completion as a Master-Agent chat bubble ("Data loaded — 1,470 rows,
35 features"). This module makes that sentence: one small LLM call per finished step, grounded
strictly in the step's actual output — real numbers only, honest about failures.

Narration is garnish by contract: ``narrate_result`` never raises. Any LLM/config/network problem
returns "" and the caller simply shows no bubble; the run itself is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import SubtaskResult

PROMPT_VERSION = "1"
_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "narrator_system.md"
_MAX_TOKENS = 200  # 1-2 short sentences; a hard cap keeps narration cheap
_OUTPUT_LIMIT = 1500  # chars of step output fed to the narrator — bounded for tokens


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _output_excerpt(output: Any, limit: int = _OUTPUT_LIMIT) -> str:
    """The step output as bounded text — real data in, token bill capped."""
    if output is None:
        return ""
    if isinstance(output, str):
        text = output
    else:
        try:
            text = json.dumps(output, default=str)
        except (TypeError, ValueError):
            text = str(output)
    return text[:limit]


def build_user_message(
    task: str,
    result: SubtaskResult,
    *,
    step_title: str = "",
    step_description: str = "",
) -> str:
    """Everything the narrator may speak about: the task, the step, and its real result."""
    lines = [
        f"USER TASK:\n{task}",
        f"STEP: {step_title or result.subtask_id}",
    ]
    if step_description:
        lines.append(f"WHAT THIS STEP WAS FOR: {step_description}")
    lines.append(f"APP THAT RAN IT: {result.app_name}")
    lines.append(f"STATUS: {result.status}")
    if result.error:
        lines.append(f"ERROR: {result.error}")
    lines.append(f"STEP RESULT (real output, may be truncated):\n{_output_excerpt(result.output)}")
    return "\n\n".join(lines)


def narrate_result(
    client: LLMClient,
    *,
    model: str,
    task: str,
    result: SubtaskResult,
    step_title: str = "",
    step_description: str = "",
) -> str:
    """The 1-2 sentence narration for one finished step, or "" if narration fails.

    Never raises: narration must not be able to break, slow, or fail a run.
    """
    try:
        request = LLMRequest(
            model=model,
            system=load_system_prompt(),
            messages=(
                {
                    "role": "user",
                    "content": build_user_message(
                        task, result, step_title=step_title, step_description=step_description
                    ),
                },
            ),
            max_tokens=_MAX_TOKENS,
        )
        return client.complete(request).strip()
    except Exception:
        return ""
