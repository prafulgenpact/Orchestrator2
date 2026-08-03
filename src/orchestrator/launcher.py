"""Auto-start a sibling app's backend on demand — the user never launches apps by hand.

When the orchestrator needs an app that isn't running, it starts that app's backend itself
(detached, so it outlives the short-lived CLI and is reused by later runs), waits until healthy,
then proceeds. Launch details per app are the recon-verified specs below. The spawner and clock are
injected so this is fully unit-testable with no real processes or network; the real spawn path is
the only thing not exercised in tests (``_spawn_uvicorn``).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import subprocess
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from orchestrator.registry import AppEntry
from orchestrator.resilience import run_with_deadline

# The folder that holds both this repo and the sibling apps (…/Desktop/Desktop).
_SIBLING_ROOT = Path(__file__).resolve().parents[4]
_HEALTH_TIMEOUT_S = 5.0
DEFAULT_START_TIMEOUT_S = 75.0  # cold start incl. model loads; bounded so a bad start never hangs
_POLL_INTERVAL_S = 1.5


@dataclass(frozen=True)
class LaunchSpec:
    """How to launch one app's backend: sibling folder, uvicorn target, and any extra env."""

    folder: str  # backend lives at <_SIBLING_ROOT>/<folder>/backend
    entrypoint: str  # uvicorn app target, e.g. "main:app" or "app.main:app"
    env: dict[str, str] = field(default_factory=dict)

    def backend_dir(self) -> Path:
        return _SIBLING_ROOT / self.folder / "backend"

    def venv_python(self) -> Path:
        return self.backend_dir() / "venv" / "bin" / "python"


# Verified against each live backend (folder name, ASGI entrypoint, startup env).
LAUNCH_SPECS: dict[str, LaunchSpec] = {
    "simulated-learning": LaunchSpec("Simulated Learning", "main:app"),
    "arxiv-papers": LaunchSpec("ArXiv papers", "main:app"),
    "coding-playground": LaunchSpec("Coding playground", "app.main:app"),
    "ai-intelligence-deck": LaunchSpec("Test", "main:app", {"STATIC_DIR": "../frontend/dist"}),
    "social-media-ai": LaunchSpec("Social Media AI", "main:app"),
    "stanford-llm": LaunchSpec("Stanford LLM", "main:app"),
    "stats-teacher": LaunchSpec("Stats Teacher", "app.main:app"),
    "teach-me": LaunchSpec("Teach Me", "main:app"),
    "github-learnings": LaunchSpec("Github Learnings", "app.main:app"),
    "blogs-playground": LaunchSpec("Blogs Playground", "main:app"),
    "research-assistant": LaunchSpec("Research Assistant", "main:app"),
}


# Each app's startup output is captured here (not /dev/null) so a boot crash — a down database, a
# missing key, an import error — is recoverable after the fact instead of invisible. Override the
# dir with ORCHESTRATOR_APP_LOG_DIR; it lives under gitignored logs/ by default.
_APP_LOG_DIR = Path(os.environ.get("ORCHESTRATOR_APP_LOG_DIR", "logs/apps"))


def app_log_path(app_id: str) -> Path:
    """Path to the captured startup log for ``app_id``."""
    return _APP_LOG_DIR / f"{app_id}.log"


def _app_id_for_spec(spec: LaunchSpec) -> str:
    """The registry app id whose launch spec this is (specs live in LAUNCH_SPECS keyed by id)."""
    for app_id, candidate in LAUNCH_SPECS.items():
        if candidate is spec:
            return app_id
    return spec.folder.lower().replace(" ", "-")  # defensive: a spec built outside LAUNCH_SPECS


def _extract_startup_error(text: str) -> str | None:
    """Pull the one salient line explaining why an app failed to boot, from its captured log.

    Prefers an explicit exception line (``OSError: ...``, an ``[Errno N]`` / "Connect call failed"),
    else the last line that mentions a failure, else the last non-empty line. None for an empty log.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    exc = [
        ln
        for ln in lines
        if re.match(r"^[A-Za-z_][\w.]*(Error|Exception|Timeout)\b.*:", ln)
        or "Errno" in ln
        or "Connect call failed" in ln
    ]
    if exc:
        return exc[-1]
    fail = [ln for ln in lines if re.search(r"startup failed|refused|failed|error", ln, re.I)]
    return fail[-1] if fail else lines[-1]


def read_startup_error(app_id: str) -> str | None:
    """The salient startup-crash line from ``app_id``'s captured log, or None if unavailable."""
    try:
        return _extract_startup_error(app_log_path(app_id).read_text(errors="replace"))
    except OSError:
        return None


def _spawn_uvicorn(spec: LaunchSpec, port: int) -> bool:  # pragma: no cover - real process spawn
    """Start the backend detached on 127.0.0.1:port. Returns False if it cannot be launched.

    Startup output is captured to ``logs/apps/<id>.log`` (truncated each attempt) so a boot failure
    surfaces its real cause instead of vanishing into /dev/null.
    """
    python = spec.venv_python()
    if not python.exists():
        return False
    try:
        _APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(app_log_path(_app_id_for_spec(spec)), "w")  # noqa: SIM115 - child keeps its fd
    except OSError:
        return False
    try:
        subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                spec.entrypoint,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(spec.backend_dir()),
            env={**os.environ, **spec.env},
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detach: survives the CLI, reused by later runs
        )
    except OSError:
        log.close()
        return False
    finally:
        log.close()  # the child keeps its own dup'd fd; we don't need ours
    return True


def is_healthy_response(status_code: int, content_type: str) -> bool:
    """Honest health verdict for a probe response.

    A real API is alive only on a 2xx. Crucially we also reject ``text/html``: an app fronted by a
    single-page-app catch-all (e.g. teach-me) returns ``200 text/html`` (its index.html) for ANY
    unmatched path — so the old ``status < 500`` check called such an app "healthy" even when its
    API layer was dead. Requiring a non-HTML 2xx makes a probe of a real JSON route the only thing
    that counts as up. Shared with the per-call health check in app_caller so both agree.
    """
    if not 200 <= status_code < 300:
        return False
    return "text/html" not in content_type.lower()


async def _health_ok(app: AppEntry, client: httpx.AsyncClient) -> bool:
    if app.base_url is None or app.health is None:
        return False
    try:
        resp = await run_with_deadline(client.get(f"{app.base_url}{app.health}"), _HEALTH_TIMEOUT_S)
    except Exception:
        return False
    return is_healthy_response(resp.status_code, resp.headers.get("content-type", ""))


def _pids_on_port(port: int) -> list[int]:  # pragma: no cover - real syscall
    """PIDs listening on 127.0.0.1:``port`` (via ``lsof``). Empty list on any error/none found."""
    try:
        proc = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for token in proc.stdout.split():
        with contextlib.suppress(ValueError):
            pids.append(int(token))
    return pids


def _cmdline(pid: int) -> str:  # pragma: no cover - real syscall
    """The full command line of ``pid`` (via ``ps``); empty string on any error."""
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip()


def _kill(pid: int) -> None:  # pragma: no cover - real syscall
    """Terminate ``pid`` (SIGTERM, then SIGKILL). Silent if it is already gone."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return


def _is_our_app_process(cmdline: str, spec: LaunchSpec, port: int) -> bool:
    """True only if ``cmdline`` is positively THIS app's own uvicorn process on ``port``.

    The safety rule for reaping: kill a process ONLY when we can identify it as this exact app's
    backend. ``ps`` shows the argv (not the working directory), so we match the three signals that
    ARE in a uvicorn launch line: the ``uvicorn`` module, this app's ASGI entrypoint, and its port.
    Matching is on whitespace-delimited TOKENS, not substrings — otherwise ``main:app`` would
    spuriously match ``app.main:app`` (a different app). Since the candidate was already found by
    ``lsof`` listening on this exact port, these together positively attribute it to this app.
    Anything we cannot attribute — a non-uvicorn server, a different entrypoint, a different port —
    is never touched.
    """
    tokens = cmdline.split()
    return "uvicorn" in tokens and spec.entrypoint in tokens and str(port) in tokens


def reap_stale_listeners(
    port: int,
    spec: LaunchSpec,
    *,
    list_pids: Callable[[int], list[int]] = _pids_on_port,
    cmdline: Callable[[int], str] = _cmdline,
    kill: Callable[[int], None] = _kill,
) -> list[int]:
    """Kill any process squatting ``port`` that is positively THIS app's own hung backend.

    The 6-day-ArXiv failure mode: the app process is still listening but answers nothing, so a
    fresh start cannot bind the port and health never recovers. Clearing the identified stale
    process lets ``ensure_started`` relaunch cleanly. Returns the PIDs killed (empty if none
    matched). Helpers are injected so the decision logic is unit-testable without real processes.
    """
    killed: list[int] = []
    for pid in list_pids(port):
        if _is_our_app_process(cmdline(pid), spec, port):
            kill(pid)
            killed.append(pid)
    return killed


async def ensure_started(
    app: AppEntry,
    client: httpx.AsyncClient,
    *,
    spawn: Callable[[LaunchSpec, int], bool] = _spawn_uvicorn,
    reap: Callable[[int, LaunchSpec], list[int]] = reap_stale_listeners,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    timeout_s: float = DEFAULT_START_TIMEOUT_S,
    interval_s: float = _POLL_INTERVAL_S,
) -> bool:
    """Ensure ``app`` is healthy, recovering a hung instance if needed. Returns True iff healthy.

    Health-first: an app already answering is used as-is (no doomed duplicate spawn). Otherwise a
    stale/hung process squatting the port is reaped first — the 6-day-ArXiv fix, where the old
    process held the port so a fresh start could never bind — then the app is (re)launched and
    health-polled. Never raises: returns False when there is no launch spec, no port, the spawn
    fails, or health does not come up within ``timeout_s`` — the caller then errors cleanly.
    """
    spec = LAUNCH_SPECS.get(app.id)
    if spec is None or app.port is None:
        return False
    if await _health_ok(app, client):
        return True  # already up — never spawn a duplicate or touch the live process
    # Unhealthy: clear a hung instance of THIS app off the port (safe: positively identified),
    # so the fresh spawn can bind. A brief pause lets the OS release the socket before we start.
    if reap(app.port, spec):
        await sleep(interval_s)
    if not spawn(spec, app.port):
        return False
    for _ in range(max(1, int(timeout_s / interval_s))):
        if await _health_ok(app, client):
            return True
        await sleep(interval_s)
    return False


async def start_all(
    apps: Iterable[AppEntry],
    client: httpx.AsyncClient,
    *,
    ensure: Callable[..., Awaitable[bool]] = ensure_started,
) -> dict[str, bool]:
    """Start + health-confirm every non-fallback app up front, concurrently (the outset preflight).

    Returns ``{app_id: healthy}``. Never raises — an app that cannot be brought up maps to False so
    the caller can report it (and the per-subtask path still applies its own fallback). Fallback
    apps (no port) are skipped. Concurrency means the wall-clock is the slowest single app, not the
    sum, and an app already running returns immediately (its health check passes).
    """
    targets = [app for app in apps if not app.fallback]
    outcomes = await asyncio.gather(
        *(ensure(app, client) for app in targets), return_exceptions=True
    )
    return {app.id: (outcome is True) for app, outcome in zip(targets, outcomes, strict=True)}
