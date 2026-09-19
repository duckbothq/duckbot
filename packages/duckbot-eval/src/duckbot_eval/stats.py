"""Scores, with how much they are worth.

Ten cases cannot tell 80% apart from 90%. A run of ten that scores eight and gets written
into a slide as "80%" has turned a coin-flip into a fact, and the person reading the
slide has no way to know. So every rate this package reports carries an interval, and the
report prints it next to the number rather than in a footnote.

The Wilson interval is used rather than the textbook normal approximation because the
normal one is wrong exactly where evaluation sets live — small n, and rates near 0 or 1,
where it happily produces bounds below zero or above one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z_95 = 1.959963984540054
"""Two-sided 95%."""


@dataclass(frozen=True)
class Rate:
    """A proportion and the interval around it."""

    passed: int
    total: int
    low: float
    high: float

    @property
    def value(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def width(self) -> float:
        return self.high - self.low

    def __str__(self) -> str:
        if not self.total:
            return "n/a (no cases)"
        return (
            f"{self.value:.0%} ({self.passed}/{self.total}, 95% CI {self.low:.0%}–{self.high:.0%})"
        )


def wilson(passed: int, total: int, z: float = Z_95) -> Rate:
    """The Wilson score interval."""
    if passed < 0 or total < 0 or passed > total:
        raise ValueError("passed must be between 0 and total")
    if total == 0:
        return Rate(0, 0, 0.0, 1.0)

    proportion = passed / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    spread = (
        z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    )
    return Rate(passed, total, max(0.0, centre - spread), min(1.0, centre + spread))


def cases_needed(expected_rate: float, half_width: float, z: float = Z_95) -> int:
    """Roughly how many cases a given precision needs.

    For answering "we have twelve cases and the interval is ±20 points; what would it
    take to get to ±5?" — usually a number large enough to end the conversation about
    whether the current figure settles anything.
    """
    if not 0.0 <= expected_rate <= 1.0:
        raise ValueError("a rate is between 0 and 1")
    if half_width <= 0:
        raise ValueError("a half-width must be positive")
    return math.ceil(z**2 * expected_rate * (1 - expected_rate) / half_width**2)
