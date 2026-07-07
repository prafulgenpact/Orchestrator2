"""Unit tests for the resilience primitives (no network; async driven via asyncio.run)."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.resilience import (
    CircuitBreaker,
    DeadlineError,
    backoff_delay,
    classify_error,
    retry_async,
    run_with_deadline,
)

# --- helpers -----------------------------------------------------------------


class _RespError(Exception):
    """Duck-typed httpx-style error carrying exc.response.status_code."""

    def __init__(self, status: object) -> None:
        super().__init__("http error")
        self.response = type("R", (), {"status_code": status})()


class _RespNoStatusError(Exception):
    """Has a response object but no status_code attribute."""

    def __init__(self) -> None:
        super().__init__("weird response")
        self.response = type("R", (), {})()


class _StatusError(Exception):
    """Carries exc.status_code directly."""

    def __init__(self, status: object) -> None:
        super().__init__("http error")
        self.status_code = status


class _FakeSleep:
    """Records requested delays instead of sleeping."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


# --- B1: run_with_deadline ---------------------------------------------------


def test_deadline_returns_value() -> None:
    async def quick() -> str:
        return "ok"

    assert asyncio.run(run_with_deadline(quick(), 1.0)) == "ok"


def test_deadline_fires_on_hang() -> None:
    async def hang() -> None:
        await asyncio.sleep(10)

    async def go() -> None:
        await run_with_deadline(hang(), 0.01)

    with pytest.raises(DeadlineError, match="0.01s deadline"):
        asyncio.run(go())


# --- B2: classify_error ------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_classify_auth_status(status: int) -> None:
    assert classify_error(_RespError(status)) == "auth"


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_classify_retry_status(status: int) -> None:
    assert classify_error(_RespError(status)) == "retry"


@pytest.mark.parametrize("status", [400, 404, 422])
def test_classify_fatal_status(status: int) -> None:
    assert classify_error(_RespError(status)) == "fatal"


def test_classify_status_via_status_code_attr() -> None:
    assert classify_error(_StatusError(503)) == "retry"


def test_classify_ignores_bool_status() -> None:
    # status_code=True must not be read as HTTP 1; falls through to fatal.
    assert classify_error(_StatusError(True)) == "fatal"


def test_classify_response_without_status_code() -> None:
    assert classify_error(_RespNoStatusError()) == "fatal"


def test_classify_status_outside_error_ranges() -> None:
    # a status is present but not 4xx/5xx (e.g. a 3xx) -> falls through to message -> fatal
    assert classify_error(_RespError(302)) == "fatal"


def test_classify_auth_hint() -> None:
    assert classify_error(Exception("Request forbidden by policy")) == "auth"


@pytest.mark.parametrize("exc", [ValueError("bad"), TypeError("bad"), KeyError("bad")])
def test_classify_fatal_types(exc: Exception) -> None:
    assert classify_error(exc) == "fatal"


def test_classify_deadline_is_retry() -> None:
    assert classify_error(DeadlineError("too slow")) == "retry"


@pytest.mark.parametrize(
    "exc",
    [asyncio.TimeoutError(), TimeoutError(), ConnectionError(), ConnectionResetError()],
)
def test_classify_retry_types(exc: BaseException) -> None:
    assert classify_error(exc) == "retry"


def test_classify_oserror_transient_hint() -> None:
    assert classify_error(OSError("connection reset by peer")) == "retry"


def test_classify_oserror_without_hint_is_fatal() -> None:
    assert classify_error(OSError("no space left on device")) == "fatal"


def test_classify_generic_transient_hint() -> None:
    assert classify_error(RuntimeError("upstream stream closed")) == "retry"


def test_classify_unknown_is_fatal() -> None:
    assert classify_error(RuntimeError("something odd")) == "fatal"


# --- B3: backoff_delay -------------------------------------------------------


def test_backoff_no_jitter_is_exponential() -> None:
    assert backoff_delay(0, 2.0, jitter=0) == 2.0
    assert backoff_delay(1, 2.0, jitter=0) == 4.0
    assert backoff_delay(2, 2.0, jitter=0) == 8.0


def test_backoff_jitter_within_band() -> None:
    for _ in range(50):
        d = backoff_delay(1, 10.0, jitter=0.2)  # base*2 = 20, +/-20%
        assert 16.0 <= d <= 24.0


def test_backoff_never_negative() -> None:
    assert backoff_delay(0, 0.0) == 0.0


# --- B3: retry_async ---------------------------------------------------------


def test_retry_async_success_first_try() -> None:
    calls = {"n": 0}
    sleep = _FakeSleep()

    async def op() -> str:
        calls["n"] += 1
        return "done"

    result = asyncio.run(retry_async(op, transient_max=2, backoff_s=1.0, sleep=sleep))
    assert result == "done"
    assert calls["n"] == 1
    assert sleep.delays == []


def test_retry_async_retries_then_succeeds() -> None:
    calls = {"n": 0}
    sleep = _FakeSleep()
    retries: list[int] = []

    async def op() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    result = asyncio.run(
        retry_async(
            op,
            transient_max=3,
            backoff_s=1.0,
            sleep=sleep,
            on_retry=lambda attempt, _exc, _delay: retries.append(attempt),
        )
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert retries == [0, 1]  # two retries before the third succeeds
    assert len(sleep.delays) == 2


def test_retry_async_exhausts_transient_max() -> None:
    calls = {"n": 0}
    sleep = _FakeSleep()

    async def op() -> str:
        calls["n"] += 1
        raise TimeoutError("always slow")

    with pytest.raises(TimeoutError):
        asyncio.run(retry_async(op, transient_max=2, backoff_s=0.5, sleep=sleep))
    assert calls["n"] == 3  # initial + 2 retries
    assert len(sleep.delays) == 2


def test_retry_async_does_not_retry_fatal() -> None:
    calls = {"n": 0}
    sleep = _FakeSleep()

    async def op() -> str:
        calls["n"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        asyncio.run(retry_async(op, transient_max=3, backoff_s=1.0, sleep=sleep))
    assert calls["n"] == 1
    assert sleep.delays == []


def test_retry_async_does_not_retry_auth() -> None:
    calls = {"n": 0}
    sleep = _FakeSleep()

    async def op() -> str:
        calls["n"] += 1
        raise _RespError(401)

    with pytest.raises(_RespError):
        asyncio.run(retry_async(op, transient_max=3, backoff_s=1.0, sleep=sleep))
    assert calls["n"] == 1


# --- B4: CircuitBreaker ------------------------------------------------------


def test_circuit_breaker_opens_after_threshold() -> None:
    cb = CircuitBreaker(threshold=3)
    assert not cb.is_open("arxiv")
    assert cb.record_failure("arxiv") == 1
    assert cb.record_failure("arxiv") == 2
    assert not cb.is_open("arxiv")
    assert cb.record_failure("arxiv") == 3
    assert cb.is_open("arxiv")
    # a different key is unaffected
    assert not cb.is_open("blogs")


def test_circuit_breaker_success_resets() -> None:
    cb = CircuitBreaker(threshold=2)
    cb.record_failure("x")
    cb.record_failure("x")
    assert cb.is_open("x")
    cb.record_success("x")
    assert not cb.is_open("x")
    assert cb.failure_count("x") == 0


def test_circuit_breaker_reset() -> None:
    cb = CircuitBreaker(threshold=1)
    cb.record_failure("a")
    cb.record_failure("b")
    cb.reset("a")
    assert not cb.is_open("a")
    assert cb.is_open("b")
    cb.reset()  # clear all
    assert not cb.is_open("b")


def test_circuit_breaker_bad_threshold() -> None:
    with pytest.raises(ValueError, match="threshold must be >= 1"):
        CircuitBreaker(threshold=0)
