"""Reliability primitives for calling apps without hanging (AC-2).

Fresh, dependency-light building blocks the app-caller/executor compose. They are
deliberately decoupled from the registry: they take plain numbers, not a ``RetrySpec``,
so this logic stays pure and unit-testable with no network.

  - ``run_with_deadline`` — a HARD wall-clock cap via ``asyncio.wait_for``. This is the
    real anti-hang guarantee: an httpx/requests ``timeout`` is a *per-chunk read* timeout,
    not a total one, so a trickling connection can block forever without this wrapper.
  - ``classify_error`` — ``"retry"`` | ``"fatal"`` | ``"auth"``. Duck-types HTTP status off
    the exception (``exc.response.status_code`` or ``exc.status_code``) so it works with
    httpx later without importing it now.
  - ``backoff_delay`` — exponential backoff with symmetric jitter.
  - ``retry_async`` — bounded retries of an async operation; retries only transient errors,
    re-raises fatal/auth immediately. ``sleep`` is injectable so tests never really wait.
  - ``CircuitBreaker`` — per-key consecutive-failure gate so a dead app is skipped, not hammered.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Literal, TypeVar

T = TypeVar("T")

ErrorClass = Literal["retry", "fatal", "auth"]

# Exception types that are always transient (worth retrying).
_RETRY_TYPES: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,  # includes ConnectionResetError etc.
)
# Exception types that are always caller/programming errors (never retry).
_FATAL_TYPES: tuple[type[BaseException], ...] = (ValueError, TypeError, KeyError)

# Message hints used only when the exception type/status is inconclusive.
_AUTH_HINTS = (
    "unauthorized",
    "forbidden",
    "invalid api key",
    "not authenticated",
    "permission denied",
)
_TRANSIENT_HINTS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "broken pipe",
    "temporarily unavailable",
    "closed",
    "reset by peer",
)


class DeadlineError(Exception):
    """An operation exceeded its wall-clock deadline (raised by run_with_deadline)."""


async def run_with_deadline(awaitable: Awaitable[T], timeout_s: float) -> T:
    """Await ``awaitable`` but cancel it and raise ``DeadlineExceeded`` after ``timeout_s``.

    Unlike a client-library read timeout, this is a hard total cap: on expiry
    ``asyncio.wait_for`` cancels the underlying task so nothing keeps running.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise DeadlineError(f"operation exceeded {timeout_s}s deadline") from exc


def _status_of(exc: BaseException) -> int | None:
    """Best-effort HTTP status from an exception, without importing httpx."""
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
    else:
        status = getattr(exc, "status_code", None)
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    return status


def classify_error(exc: BaseException) -> ErrorClass:
    """Classify an exception as retryable, fatal, or an auth failure."""
    status = _status_of(exc)
    if status is not None:
        if status in (401, 403):
            return "auth"
        if status in (408, 429) or 500 <= status < 600:
            return "retry"
        if 400 <= status < 500:
            return "fatal"

    message = str(exc).lower()
    if any(hint in message for hint in _AUTH_HINTS):
        return "auth"
    if isinstance(exc, _FATAL_TYPES):
        return "fatal"
    if isinstance(exc, (DeadlineError, *_RETRY_TYPES)):
        return "retry"
    if isinstance(exc, OSError) and any(hint in message for hint in _TRANSIENT_HINTS):
        return "retry"
    if any(hint in message for hint in _TRANSIENT_HINTS):
        return "retry"
    return "fatal"


def backoff_delay(
    attempt: int, base_s: float, *, factor: float = 2.0, jitter: float = 0.2
) -> float:
    """Exponential backoff for a 0-based attempt, with +/- ``jitter`` fractional noise.

    attempt 0 -> ~base_s, attempt 1 -> ~base_s*factor, ... Never negative.
    """
    raw = base_s * (factor**attempt)
    if jitter:
        raw *= 1 + random.uniform(-jitter, jitter)
    return max(0.0, raw)


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    transient_max: int,
    backoff_s: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Call ``operation`` (a zero-arg async factory), retrying only transient failures.

    Retries up to ``transient_max`` times with exponential backoff+jitter. Fatal and auth
    errors re-raise immediately. ``sleep`` is injectable for deterministic tests.
    """
    attempt = 0
    while True:
        try:
            return await operation()
        except (
            Exception
        ) as exc:  # not BaseException: never swallow CancelledError/KeyboardInterrupt
            if classify_error(exc) != "retry" or attempt >= transient_max:
                raise
            delay = backoff_delay(attempt, backoff_s)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            await sleep(delay)
            attempt += 1


class CircuitBreaker:
    """Per-key consecutive-failure gate. Opens after ``threshold`` failures in a row.

    A success clears the key's count. Intended scope is one run (or one turn): once open
    for an app, callers should skip that app and report it rather than keep calling.
    """

    def __init__(self, threshold: int = 3) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self.threshold = threshold
        self._failures: dict[str, int] = {}

    def is_open(self, key: str) -> bool:
        return self._failures.get(key, 0) >= self.threshold

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)

    def record_failure(self, key: str) -> int:
        self._failures[key] = self._failures.get(key, 0) + 1
        return self._failures[key]

    def failure_count(self, key: str) -> int:
        return self._failures.get(key, 0)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._failures.clear()
        else:
            self._failures.pop(key, None)
