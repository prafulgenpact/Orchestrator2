"""Command-line entry point for the dry-run orchestrator.

Usage: ``python -m orchestrator "plan my week of learning transformers"``. Prints the
recognized intent, the subtask breakdown (sequential and parallel), and the app that
would handle each subtask — then stops. No app is invoked.

Exit codes: 0 success, 2 usage (argparse), 3 config/registry/credential error,
4 planning failure (the model could not produce a valid plan).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

from orchestrator.executor import execute_plan
from orchestrator.llm import VALID_MODES, get_client
from orchestrator.llm.base import LLMClient, LLMError
from orchestrator.llm.foundry import resolve_model
from orchestrator.models import Plan, PlanResult
from orchestrator.planner import PlannerError, plan_task
from orchestrator.registry import Registry, RegistryError, load_registry
from orchestrator.render import render_execution, render_human, render_json


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description=(
            "Dry-run orchestrator: decompose a task and report which apps would "
            "handle it. No app is invoked."
        ),
    )
    parser.add_argument("task", help="the natural-language task to plan")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually invoke the selected apps and show their real results (default: dry run)",
    )
    parser.add_argument("--json", action="store_true", help="emit the plan as JSON")
    parser.add_argument("--model", help="override the model id")
    parser.add_argument("--registry", help="path to a registry apps.json (default: bundled)")
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        default=os.environ.get("AGENT_LLM_MODE") or "live",
        help="LLM mode: live (default), record, or replay",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="max times to feed a validation error back to the model (default 2)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, client: LLMClient | None = None) -> int:
    args = _parse_args(argv)

    try:
        registry = load_registry(Path(args.registry) if args.registry else None)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if client is None:
        try:
            client = get_client(args.mode)
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3

    model = resolve_model(args.model)
    try:
        plan = plan_task(client, registry, args.task, model=model, max_retries=args.max_retries)
    except (PlannerError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    if args.execute:
        try:
            result = asyncio.run(_execute(plan, registry, client, model))
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 4
        print(render_execution(result))
        return 0

    print(render_json(plan) if args.json else render_human(plan))
    return 0


async def _execute(plan: Plan, registry: Registry, client: LLMClient, model: str) -> PlanResult:
    async with httpx.AsyncClient() as http_client:
        return await execute_plan(
            plan, registry, llm_client=client, http_client=http_client, model=model
        )
