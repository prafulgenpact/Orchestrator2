"""Web connector: serve the Atelier UI and stream a live orchestrator run to the browser.

The browser opens ``GET /run?task=...`` as a Server-Sent Events (SSE) stream. This module does not
plan, execute, or synthesize anything itself — it calls the orchestrator's existing pipeline
(``plan_task`` -> ``execute_plan(progress=...)`` -> ``synthesize(on_delta=...)``) and relays what
that pipeline already emits, event by event, as it happens:

    status  -> a one-line "what's happening now" note
    plan    -> the decomposed plan (feeds the progress feed + agent trace)
    progress-> each executor progress line, live (incl. slow-step heartbeats)
    result  -> one executed subtask's real app output (feeds a canvas card)
    answer  -> a delta of the streamed final answer
    final   -> the whole answer + provenance sources
    error   -> any failure, surfaced instead of raised
    done    -> the stream is complete

The logic lives in the pure ``run_events`` generator (unit-tested with the backend calls
monkeypatched). The thin HTTP/socket/asyncio shell below it is exercised by the live acceptance
run, not by unit tests, so it is marked ``# pragma: no cover``.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from orchestrator.llm.base import LLMClient
from orchestrator.models import Plan, PlanResult
from orchestrator.planner import plan_task
from orchestrator.registry import Registry
from orchestrator.synthesis import synthesize

Event = tuple[str, dict[str, Any]]

# The finalised UI ships in this repo's web/ folder; $ATELIER_UI overrides it (e.g. to serve the
# app-prototypes design file during development).
DEFAULT_UI = Path(__file__).resolve().parents[2] / "web" / "atelier-workspace.html"


def ui_path() -> Path:
    """HTML page to serve: ``$ATELIER_UI`` if set, else the bundled ``web/`` default."""
    override = os.environ.get("ATELIER_UI")
    return Path(override).expanduser() if override else DEFAULT_UI


def sse(event: str, data: dict[str, Any]) -> bytes:
    """One event in the SSE wire format: ``event: <name>\\ndata: <json>\\n\\n`` (UTF-8 bytes)."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


def _collect_images(result: PlanResult, limit: int = 8) -> list[str]:
    """Base64 PNG charts produced across the run's successful steps (deduped, capped).

    Carried onto the FINAL answer so the whole deliverable — the blog — shows its charts, not just
    the intermediate step that made them. Reads each ok result's ``output['images']`` (the kernel's
    displayed figures the executor already captured)."""
    seen: set[str] = set()
    images: list[str] = []
    for r in result.results:
        if r.status != "ok" or not isinstance(r.output, dict):
            continue
        for img in r.output.get("images") or []:
            if isinstance(img, str) and img and img not in seen:
                seen.add(img)
                images.append(img)
                if len(images) >= limit:
                    return images
    return images


def _execute_plan_sync(
    plan: Plan,
    registry: Registry,
    client: LLMClient,
    model: str,
    progress: Callable[[str], None],
    on_result: Callable[[Any], None],
) -> PlanResult:  # pragma: no cover - asyncio + httpx + live apps, covered by the acceptance run
    """Run the plan against the real apps, forwarding executor progress lines to ``progress`` and
    each subtask's result to ``on_result`` the moment that subtask finishes.

    Mirrors the CLI's execute path (start every app, then execute) but with injected callbacks so
    the run can be streamed. Isolated here so ``run_events`` stays synchronous and unit-testable by
    monkeypatching this one function.
    """
    import asyncio

    import httpx

    from orchestrator.executor import execute_plan
    from orchestrator.launcher import start_all

    async def _go() -> PlanResult:
        async with httpx.AsyncClient() as http_client:
            progress("Starting apps…")
            await start_all(registry.apps, http_client)
            return await execute_plan(
                plan,
                registry,
                llm_client=client,
                http_client=http_client,
                model=model,
                progress=progress,
                on_result=on_result,
            )

    return asyncio.run(_go())


def run_events(task: str, *, client: LLMClient, registry: Registry, model: str) -> Iterator[Event]:
    """Run ``task`` and yield the whole run as a live, ordered event stream.

    Planning happens inline; execution + synthesis run on a worker thread whose progress/answer
    callbacks push onto a queue this generator drains, so browser updates arrive as they happen
    rather than all at the end. Any failure becomes a single ``error`` event — never an exception.
    """
    yield ("status", {"message": "Planning your task…"})
    try:
        plan = plan_task(client, registry, task, model=model)
    except Exception as exc:  # - report planning failure to the browser, don't crash
        yield ("error", {"message": str(exc), "stage": "plan"})
        yield ("done", {})
        return

    yield ("plan", plan.to_dict())
    deps = {s.id: s.depends_on for s in plan.subtasks}

    bus: queue.Queue[Event | None] = queue.Queue()

    def worker() -> None:
        try:
            result = _execute_plan_sync(
                plan,
                registry,
                client,
                model,
                lambda m: bus.put(("progress", {"message": m})),
                lambda r: bus.put(("result", r.to_dict())),  # streamed as each subtask finishes
            )
            synth = synthesize(
                client,
                result,
                model=model,
                subtask_deps=deps,
                on_delta=lambda d: bus.put(("answer", {"delta": d})),
            )
            bus.put(
                (
                    "final",
                    {
                        "answer": synth.answer,
                        "sources": list(synth.sources),
                        "mode": synth.mode,
                        "images": _collect_images(result),
                    },
                )
            )
        except Exception as exc:  # - surface any run failure as one event
            bus.put(("error", {"message": str(exc), "stage": "execute"}))
        finally:
            bus.put(None)  # sentinel: worker finished

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        item = bus.get()
        if item is None:
            break
        yield item

    yield ("done", {})


class _Handler(BaseHTTPRequestHandler):  # pragma: no cover - socket I/O, run manually in acceptance
    """Serves the UI at ``/`` and a live SSE run at ``/run?task=...``."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base signature name
        pass  # keep the connector quiet; the run itself is the interesting output

    def _client(self) -> tuple[LLMClient, Registry, str]:
        from orchestrator.llm import get_client
        from orchestrator.llm.foundry import resolve_model
        from orchestrator.registry import load_registry

        return get_client("live"), load_registry(), resolve_model(None)

    def do_GET(self) -> None:  # noqa: N802 - name mandated by BaseHTTPRequestHandler
        route = urlparse(self.path)
        if route.path in ("/", "/index.html"):
            self._serve_ui()
        elif route.path == "/run":
            task = (parse_qs(route.query).get("task") or [""])[0].strip()
            self._serve_run(task)
        else:
            self.send_error(404, "not found")

    def _serve_ui(self) -> None:
        try:
            body = ui_path().read_bytes()
        except OSError as exc:
            self.send_error(500, f"cannot read UI: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_run(self, task: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        if not task:
            self._write(sse("error", {"message": "empty task"}))
            self._write(sse("done", {}))
            return
        try:
            client, registry, model = self._client()
            for event, data in run_events(task, client=client, registry=registry, model=model):
                self._write(sse(event, data))
        except (BrokenPipeError, ConnectionResetError):
            return  # the browser navigated away mid-run; nothing to do

    def _write(self, chunk: bytes) -> None:
        self.wfile.write(chunk)
        self.wfile.flush()


def _is_benign_disconnect(exc: BaseException | None) -> bool:
    """True for the everyday 'the client closed the socket' errors — a browser preconnecting,
    refreshing, or navigating away mid-stream. These are not server faults and must not log a
    traceback (they raise in the base handler's request read, before our handler runs)."""
    return isinstance(exc, ConnectionResetError | BrokenPipeError | ConnectionAbortedError)


class _ConnectorHTTPServer(ThreadingHTTPServer):  # pragma: no cover - socket shell, run manually
    """ThreadingHTTPServer that stays quiet when a browser hangs up early, but still reports real
    errors."""

    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        if _is_benign_disconnect(sys.exc_info()[1]):
            return  # expected client disconnect — ignore instead of dumping a traceback
        super().handle_error(request, client_address)


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover - process entry
    """Run the connector until interrupted."""
    httpd = _ConnectorHTTPServer((host, port), _Handler)
    print(f"Atelier connector → http://{host}:{port}  (serving {ui_path()})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":  # pragma: no cover - process entry
    serve(port=int(os.environ.get("ATELIER_PORT", "8080")))
