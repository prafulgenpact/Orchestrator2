"""Unit tests for the sample module — replace alongside src/."""

from __future__ import annotations

import pytest

from calculator import add, divide


def test_add() -> None:
    assert add(2, 2) == 4
    assert add(-1, 1) == 0
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_divide() -> None:
    assert divide(10, 2) == 5
    assert divide(1, 4) == 0.25


def test_divide_by_zero_raises() -> None:
    with pytest.raises(ValueError, match="division by zero"):
        divide(1, 0)
