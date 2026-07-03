"""Sample module — replace with your project code.

Exists so the scaffold verifies green out of the box and you can watch the
whole contract (verify → proof → seal → push) work before writing real code.
"""

from __future__ import annotations


def add(a: float, b: float) -> float:
    """Return the sum of a and b."""
    return a + b


def divide(a: float, b: float) -> float:
    """Divide a by b, raising ValueError on division by zero."""
    if b == 0:
        raise ValueError("division by zero")
    return a / b
